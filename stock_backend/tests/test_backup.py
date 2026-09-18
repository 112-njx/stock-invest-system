"""G05 · P1-1 备份与灾难恢复测试。

覆盖三类，全部使用真实文件系统 / 真实 Redis / 真实子进程，不使用 mock：

1. **纯逻辑**（任何环境都跑）：保留期清理、文件镜像、异地模拟模式、磁盘用量、状态读写、
   pg 客户端解析、编排失败路径；
2. **部署产物**（任何环境都跑）：解析真实 compose YAML 断言 Redis AOF+RDB 与 PG WAL 归档配置、
   用 `bash -n` 校验备份脚本语法、断言 Celery beat/路由注册；
3. **集成**（需 pg 客户端或可用 docker PG 容器）：真实 `pg_dump` + 恢复到临时库比对行数、
   真实 `pg_basebackup` 产出双 tar。

第 3 类在既无 `pg_dump` 又无 docker 的环境会显式 skip 并给出原因 —— 这是环境门控，
不是用 skip 掩盖失败：本机（Windows 开发机）走 `BACKUP_PG_DUMP_MODE=auto` 经 db 容器执行，实测可跑。
"""

import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from app.core.config import get_settings
from app.services import backup_service
from app.services.backup_service import BackupError

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_COMPOSE = REPO_ROOT / "deploy" / "docker-compose.dev.yml"
PROD_COMPOSE = REPO_ROOT / "deploy" / "docker-compose.yml"


@contextmanager
def settings_override(**kwargs):
    """临时覆盖配置项并在结束后还原（get_settings 是 lru_cache 单例，改的就是同一对象）。"""
    settings = get_settings()
    saved = {key: getattr(settings, key) for key in kwargs}
    for key, value in kwargs.items():
        setattr(settings, key, value)
    try:
        yield settings
    finally:
        for key, value in saved.items():
            setattr(settings, key, value)


def _age(path: Path, days: int) -> None:
    """把文件/目录的 mtime 改成 days 天前（用于保留期清理断言）。"""
    ts = (datetime.now(UTC) - timedelta(days=days)).timestamp()
    os.utime(path, (ts, ts))


def _pg_client_available() -> bool:
    try:
        backup_service.resolve_pg_client(None, "pg_dump")
        return True
    except BackupError:
        return False


needs_pg_client = pytest.mark.skipif(
    not _pg_client_available(),
    reason="环境无 pg_dump 客户端且无可用 docker PG 容器（需 postgresql-client 或 BACKUP_PG_DUMP_MODE=docker）",
)


# --------------------------------------------------------------------------- #
# 1. 纯逻辑
# --------------------------------------------------------------------------- #
def test_prune_dir_removes_only_expired_entries(tmp_path):
    """保留期清理只删过期条目，未过期的一律保留（按 mtime 判定）。"""
    old_file = tmp_path / "old.dump"
    old_file.write_text("old")
    _age(old_file, 40)
    fresh_file = tmp_path / "fresh.dump"
    fresh_file.write_text("fresh")
    old_dir = tmp_path / "old_dir"
    old_dir.mkdir()
    (old_dir / "x").write_text("x")
    _age(old_dir, 40)

    removed = backup_service.prune_dir(tmp_path, retain_days=30)

    assert sorted(removed) == ["old.dump", "old_dir"]
    assert not old_file.exists()
    assert not old_dir.exists()
    assert fresh_file.exists()


def test_prune_dir_disabled_or_missing_dir_is_noop(tmp_path):
    """retain_days<=0 或目录不存在时不删任何东西，也不抛错。"""
    f = tmp_path / "a.dump"
    f.write_text("a")
    _age(f, 999)

    assert backup_service.prune_dir(tmp_path, retain_days=0) == []
    assert f.exists()
    assert backup_service.prune_dir(tmp_path / "nope", retain_days=7) == []


def test_prune_backups_covers_every_category(tmp_path):
    """prune_backups 覆盖 full/base/wal/files/manifests 五类，各自按配置天数清理。"""
    root = tmp_path / "backups"
    stale = []
    for sub in ("pg/full", "pg/base", "pg/wal", "files", "manifests"):
        d = root / sub
        d.mkdir(parents=True)
        item = d / "stale"
        item.write_text("stale")
        _age(item, 60)
        stale.append(item)
        fresh = d / "fresh"
        fresh.write_text("fresh")

    with settings_override(BACKUP_DIR=str(root)):
        removed = backup_service.prune_backups()

    assert set(removed) == {"full", "base", "wal", "files", "manifests"}
    for item in stale:
        assert not item.exists(), item
        assert (item.parent / "fresh").exists()


def test_backup_files_mirrors_sources_and_reports_stats(tmp_path):
    """文件镜像把记忆/导出目录内容完整复制到 files/YYYYMMDD/，并报告文件数与字节数。"""
    memory = tmp_path / "memory"
    (memory / "554").mkdir(parents=True)
    (memory / "554" / "fact.md").write_text("记忆内容", encoding="utf-8")
    exports = tmp_path / "exports"
    exports.mkdir()
    (exports / "export.zip").write_bytes(b"PK\x03\x04" + b"x" * 100)
    backups = tmp_path / "backups"

    with settings_override(
        BACKUP_DIR=str(backups),
        MEMORY_DIR=str(memory),
        EXPORT_DIR=str(exports),
    ):
        result = backup_service.backup_files()

    assert result["day"] == datetime.now(UTC).strftime("%Y%m%d")
    by_name = {s["name"]: s for s in result["sources"]}
    assert set(by_name) == {"memory", "exports"}

    assert by_name["memory"]["files"] == 1
    assert by_name["memory"]["size_bytes"] == len("记忆内容".encode())
    assert (Path(result["dest"]) / "memory" / "554" / "fact.md").read_text(encoding="utf-8") == "记忆内容"

    assert by_name["exports"]["files"] == 1
    assert by_name["exports"]["size_bytes"] == 104
    assert (Path(result["dest"]) / "exports" / "export.zip").read_bytes().endswith(b"x" * 100)


def test_backup_files_reports_missing_source_without_failing(tmp_path):
    """源目录不存在时标记 skipped，不影响其它源（记忆目录尚未创建的首启场景）。"""
    exports = tmp_path / "exports"
    exports.mkdir()
    (exports / "a.zip").write_bytes(b"a")

    with settings_override(
        BACKUP_DIR=str(tmp_path / "backups"),
        MEMORY_DIR=str(tmp_path / "no-such-memory"),
        EXPORT_DIR=str(exports),
    ):
        result = backup_service.backup_files()

    by_name = {s["name"]: s for s in result["sources"]}
    assert by_name["memory"]["skipped"] == "源目录不存在"
    assert by_name["exports"]["files"] == 1


def test_offsite_simulated_mode_when_remote_unset(tmp_path):
    """RCLONE_REMOTE 未配置 → 模拟模式：不算失败、不真同步，保留期仍如实回报。"""
    with settings_override(BACKUP_DIR=str(tmp_path), RCLONE_REMOTE="", BACKUP_OFFSITE_RETAIN_DAYS=90):
        result = backup_service.sync_offsite()

    assert result["mode"] == "simulated"
    assert result["synced"] is False
    assert result["retain_days"] == 90


def test_offsite_reports_failure_when_rclone_missing(tmp_path):
    """配了远端但机器上没有 rclone → 明确失败（而非静默成功）。"""
    with settings_override(
        BACKUP_DIR=str(tmp_path),
        RCLONE_REMOTE="oss:test-bucket",
        RCLONE_BIN=str(tmp_path / "definitely-not-rclone"),
    ):
        result = backup_service.sync_offsite()

    assert result["mode"] == "failed"
    assert result["synced"] is False
    assert "rclone" in result["error"]


def test_disk_usage_matches_real_filesystem(tmp_path):
    """磁盘用量取自真实文件系统，百分比与 shutil 口径一致。"""
    with settings_override(BACKUP_DIR=str(tmp_path / "backups"), BACKUP_DISK_MIN_FREE_PCT=15.0):
        result = backup_service.disk_usage()

    total, used, free = shutil.disk_usage(tmp_path / "backups")
    assert result["total_bytes"] == total
    assert result["free_bytes"] == free
    assert 0.0 <= result["free_pct"] <= 100.0
    assert result["low"] is (result["free_pct"] < 15.0)


def test_status_roundtrip_and_staleness(tmp_path):
    """状态落盘后可读回；超过 BACKUP_MAX_AGE_HOURS 判定为过期。"""
    root = tmp_path / "backups"
    root.mkdir()
    with settings_override(BACKUP_DIR=str(root), BACKUP_MAX_AGE_HOURS=26):
        fresh = {
            "ok": True,
            "finished_at": datetime.now(UTC).isoformat(),
            "steps": {"pg_dump": {"size_bytes": 12345}},
        }
        path = backup_service.write_status(fresh)
        assert path == root / "status.json"
        status = backup_service.backup_status()
        assert status["ok"] is True
        assert status["stale"] is False
        assert 0 <= status["age_hours"] < 1

        stale = {
            "ok": True,
            "finished_at": (datetime.now(UTC) - timedelta(hours=40)).isoformat(),
            "steps": {"pg_dump": {"size_bytes": 1}},
        }
        backup_service.write_status(stale)
        assert backup_service.backup_status()["stale"] is True


def test_status_missing_or_corrupt_is_reported_not_raised(tmp_path):
    """没有 status.json / 文件损坏时返回可判定的状态，不抛异常（/metrics 采集依赖）。"""
    root = tmp_path / "backups"
    root.mkdir()
    with settings_override(BACKUP_DIR=str(root)):
        assert backup_service.backup_status()["reason"] == "no_status"

        (root / "status.json").write_text("{not json", encoding="utf-8")
        broken = backup_service.backup_status()
        assert broken["ok"] is False
        assert broken["reason"] == "unreadable"


def test_archive_status_reports_server_settings(tmp_path):
    """归档状态取自真实数据库（SHOW archive_mode/command/wal_level）。"""
    with settings_override(PG_ARCHIVE_DIR=""):
        info = backup_service.archive_status()

    assert info["archive_mode"] in ("on", "off")
    assert info["wal_level"] in ("replica", "logical", "minimal")
    assert isinstance(info["archive_command"], str)
    assert info["enabled"] is (info["archive_mode"] == "on")
    assert info["wal_files"] is None  # 未配置归档目录时不谎报文件数


def test_archive_status_counts_wal_files_when_dir_present(tmp_path):
    """配置了归档目录且目录存在时，回报真实文件数。"""
    wal = tmp_path / "wal"
    wal.mkdir()
    (wal / "000000010000000000000001").write_bytes(b"wal")
    (wal / "000000010000000000000002").write_bytes(b"wal")

    with settings_override(PG_ARCHIVE_DIR=str(wal)):
        assert backup_service.archive_status()["wal_files"] == 2


def test_full_backup_disabled_skips_everything(tmp_path):
    """BACKUP_ENABLED=false 时直接跳过，不产生任何产物。"""
    root = tmp_path / "backups"
    with settings_override(BACKUP_DIR=str(root), BACKUP_ENABLED=False):
        result = backup_service.run_full_backup()

    assert result["ok"] is True
    assert result["skipped"] == "BACKUP_ENABLED=false"
    assert result["steps"] == {}


def test_full_backup_records_step_error_and_marks_failed(tmp_path):
    """pg_dump 不可用时：编排不抛异常、失败写进清单与 status.json 且 ok=false（供告警）。"""
    root = tmp_path / "backups"
    with settings_override(
        BACKUP_DIR=str(root),
        BACKUP_ENABLED=True,
        BACKUP_PG_DUMP_MODE="local",
        BACKUP_PG_DUMP_BIN=str(tmp_path / "no-such-pg_dump"),
        MEMORY_DIR=str(tmp_path / "memory"),
        EXPORT_DIR=str(tmp_path / "exports"),
        RCLONE_REMOTE="",
    ):
        result = backup_service.run_full_backup()
        status = backup_service.backup_status()

    assert result["ok"] is False
    assert "BACKUP_PG_DUMP_MODE=local" in result["steps"]["pg_dump"]["error"]
    assert result["steps"].get("archive_check") is None  # pg_dump 失败 → 不产生归档校验步骤
    assert status["ok"] is False
    assert status["stale"] is False  # 刚跑完，不是"过期"而是"失败"


# --------------------------------------------------------------------------- #
# pg 客户端解析
# --------------------------------------------------------------------------- #
def test_resolve_pg_client_prefers_local_binary(tmp_path):
    """local 模式使用配置的可执行文件（此处用真实存在的 python 解释器代替 pg_dump 验证解析）。"""
    with settings_override(BACKUP_PG_DUMP_MODE="local", BACKUP_PG_DUMP_BIN=sys.executable):
        argv, mode = backup_service.resolve_pg_client(None, "pg_dump")

    assert mode == "local"
    assert Path(argv[0]).samefile(sys.executable)


def test_resolve_pg_client_raises_for_missing_local_binary(tmp_path):
    """local 模式找不到可执行文件必须报错，不能悄悄降级。"""
    with settings_override(BACKUP_PG_DUMP_MODE="local", BACKUP_PG_DUMP_BIN=str(tmp_path / "nope")):
        with pytest.raises(BackupError, match="找不到可执行文件"):
            backup_service.resolve_pg_client(None, "pg_dump")


def test_resolve_pg_client_rejects_unknown_mode():
    with settings_override(BACKUP_PG_DUMP_MODE="banana"):
        with pytest.raises(BackupError, match="未知的 BACKUP_PG_DUMP_MODE"):
            backup_service.resolve_pg_client(None, "pg_dump")


def test_resolve_pg_client_auto_falls_back_to_docker():
    """auto 模式在本机无客户端时退回 docker exec（宿主开发环境的标准路径）。"""
    if not shutil.which("docker"):
        pytest.skip("本机无 docker，无法验证 auto→docker 回退")
    with settings_override(
        BACKUP_PG_DUMP_MODE="auto",
        BACKUP_PG_DUMP_BIN="definitely-not-a-real-pg_dump-binary",
        BACKUP_PG_CONTAINER="some-container",
    ):
        argv, mode = backup_service.resolve_pg_client(None, "pg_dump")

    assert mode == "docker"
    assert argv == ["docker", "exec", "-i", "some-container", "pg_dump"]


# --------------------------------------------------------------------------- #
# 2. 部署产物（真实 compose YAML / 脚本 / Celery 注册表）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("compose_path", [DEV_COMPOSE, PROD_COMPOSE], ids=["dev", "prod"])
def test_redis_persistence_enabled_in_compose(compose_path):
    """Redis 必须同时开 AOF（everysec）与 RDB（save 60 1000）——两者缺一即为验收不达标。"""
    command = yaml.safe_load(compose_path.read_text(encoding="utf-8"))["services"]["redis"]["command"]
    joined = " ".join(str(c) for c in command)

    assert "--appendonly" in joined and "yes" in joined
    assert "--appendfsync" in joined and "everysec" in joined
    assert "--save" in joined and "60" in joined and "1000" in joined


@pytest.mark.parametrize("compose_path", [DEV_COMPOSE, PROD_COMPOSE], ids=["dev", "prod"])
def test_pg_wal_archiving_enabled_in_compose(compose_path):
    """db 容器必须开 archive_mode=on 且 archive_command 指向挂载的归档卷，支持 PITR。"""
    services = yaml.safe_load(compose_path.read_text(encoding="utf-8"))["services"]
    db = services["db"]
    joined = " ".join(str(c) for c in db["command"])

    assert "archive_mode=on" in joined
    assert "wal_level=replica" in joined
    assert "archive_timeout=" in joined  # 低写入库也要有稳定的恢复点粒度
    assert "%f" in joined and "%p" in joined and "/wal-archive" in joined

    # 归档卷必须声明，并同时挂进 db（可写）与 api/worker（只读，供监控读文件数）
    volumes = yaml.safe_load(compose_path.read_text(encoding="utf-8"))["volumes"]
    assert "pgwal" in volumes
    assert "pgwal:/wal-archive" in db["volumes"]
    assert "pgwal:/wal-archive:ro" in services["api"]["volumes"]
    assert "pgwal:/wal-archive:ro" in services["worker"]["volumes"]

    # 归档卷初始属主是 root，postgres(999) 写不进去 → 必须有一次性 sidecar 先改属主
    assert services["wal-init"]["command"][-1].endswith("chown -R 999:999 /wal-archive")
    assert db["depends_on"]["wal-init"]["condition"] == "service_completed_successfully"


@pytest.mark.parametrize("compose_path", [DEV_COMPOSE, PROD_COMPOSE], ids=["dev", "prod"])
def test_backup_queue_registered_on_worker(compose_path):
    """worker 的 -Q 必须包含 backup 队列，否则备份任务无人消费（静默不执行）。"""
    services = yaml.safe_load(compose_path.read_text(encoding="utf-8"))["services"]
    command = services["worker"]["command"]
    queue_index = command.index("-Q") + 1

    assert "backup" in command[queue_index].split(",")


@pytest.mark.parametrize("script", ["backup_pg.sh", "verify_backup.sh"])
def test_backup_scripts_are_valid_and_documented(script):
    """备份脚本语法合法（bash -n 真实解析），且注明了用法与退出码。"""
    if not shutil.which("bash"):
        pytest.skip("本机无 bash，无法做脚本语法校验")
    path = REPO_ROOT / "stock_backend" / "scripts" / script
    # 在脚本所在目录以相对名调用：Git Bash 会把 "D:\..." 这类 Windows 绝对路径吃掉反斜杠
    proc = subprocess.run(["bash", "-n", path.name], capture_output=True, text=True, cwd=str(path.parent), check=False)

    assert proc.returncode == 0, proc.stderr
    text = path.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    assert "app.services.backup_service" in text


def test_celery_registers_backup_tasks_and_schedule():
    """四个备份任务必须注册、路由到 backup 队列、并按验收要求排到凌晨窗口。"""
    from app.worker.celery_app import celery_app

    expected = {
        "app.worker.tasks.backup_tasks.backup_daily",
        "app.worker.tasks.backup_tasks.backup_base_weekly",
        "app.worker.tasks.backup_tasks.offsite_sync_daily",
        "app.worker.tasks.backup_tasks.verify_backup_weekly",
    }
    assert expected <= set(celery_app.tasks)
    assert celery_app.conf.task_routes["app.worker.tasks.backup_tasks.*"] == {"queue": "backup"}

    # 按 crontab 字段断言（str(crontab) 返回的是带后缀的 repr，不能直接比字符串）
    schedule = celery_app.conf.beat_schedule

    daily = schedule["backup-daily"]["schedule"]
    assert (daily.hour, daily.minute) == ({2}, {0})  # 每日凌晨 2:00 全量备份

    base = schedule["backup-base-weekly"]["schedule"]
    assert (base.day_of_week, base.hour, base.minute) == ({0}, {2}, {45})  # 周日 02:45 物理基线

    offsite = schedule["backup-offsite-daily"]["schedule"]
    assert (offsite.hour, offsite.minute) == ({2}, {30})  # 每日 02:30 异地同步

    verify = schedule["backup-verify-weekly"]["schedule"]
    assert (verify.day_of_week, verify.hour, verify.minute) == ({0}, {3}, {30})  # 周日 03:30 恢复演练


def test_disaster_recovery_doc_covers_all_four_recovery_paths():
    """恢复演练文档必须覆盖 PG 全量 / PITR / Redis / 文件四条恢复路径，且步骤可执行。"""
    doc = REPO_ROOT / "docs" / "ops" / "disaster_recovery.md"
    text = doc.read_text(encoding="utf-8")

    for heading in (
        "## 3. 恢复演练：PostgreSQL 逻辑全量恢复",
        "## 4. 恢复演练：PITR 时间点恢复",
        "## 5. 恢复演练：Redis 恢复",
        "## 6. 恢复演练：文件恢复",
    ):
        assert heading in text
    assert "pg_restore" in text and "recovery.signal" in text and "restore_command" in text
    assert "RCLONE_REMOTE" in text and "backup_last_success_age_seconds" in text


# --------------------------------------------------------------------------- #
# 3. 集成（真实 pg_dump / pg_basebackup / pg_restore）
# --------------------------------------------------------------------------- #
@needs_pg_client
def test_pg_dump_produces_readable_archive(tmp_path):
    """真实执行 pg_dump -Fc，产物能被 pg_restore --list 读出（识别截断/损坏）。"""
    with settings_override(BACKUP_DIR=str(tmp_path / "backups")):
        entry = backup_service.run_pg_dump()
        assert Path(entry["path"]).is_file()
        assert entry["size_bytes"] > 0
        assert len(entry["sha256"]) == 64
        assert entry["client_major"] >= 16  # 服务端为 PG16，客户端主版本必须 ≥
        assert entry["mode"] in ("local", "docker")
        assert backup_service.latest_dump() == Path(entry["path"])

        archive = backup_service.verify_archive(Path(entry["path"]))
        assert archive["ok"] is True
        assert archive["entries"] > 100  # 本项目 370+ 张表 + 索引/约束/序列

        # 部分文件（.part）不得被当成有效备份
        assert list(Path(entry["path"]).parent.glob("*.part")) == []


@needs_pg_client
def test_pg_dump_version_check_passes_against_running_server(tmp_path):
    """客户端主版本必须 ≥ 服务端主版本，否则 pg_dump 会拒绝执行。"""
    with settings_override(BACKUP_DIR=str(tmp_path / "backups")):
        version = backup_service.check_client_version()

    assert version["client_major"] >= version["server_major"]
    assert version["server_major"] == 16  # 本项目服务端为 PG16（pgvector/pgvector:pg16）
    assert version["mode"] in ("local", "docker")


@needs_pg_client
def test_restore_into_temp_db_is_complete_and_cleans_up(tmp_path):
    """恢复演练：全量备份 → 临时库 → 校验完整且不超出源库 → 临时库被清理。

    **不断言"行数完全相等"**：源库是活的，dump 与比对之间的任何写入都会让两边不等，
    那种断言在并发测试/生产每周演练里会误报。校验口径见 verify_restore 文档字符串。
    """
    settings = get_settings()
    # 库名带进程号：本仓库多泳道 agent 会并发跑全库 pytest，同名临时库会互相 DROP/CREATE 打架
    verify_db = f"stock_invest_verify_test_{os.getpid()}"
    with settings_override(BACKUP_DIR=str(tmp_path / "backups"), BACKUP_VERIFY_DB=verify_db):
        entry = backup_service.run_pg_dump()
        result = backup_service.verify_restore()

        assert result["ok"] is True, result
        assert result["dump"] == entry["path"]
        assert result["restore_exit"] == 0
        assert result["restore_errors"] == []
        assert result["archive_entries"] > 100

        # schema 完整：恢复库表数与源库一致（表只在迁移时变化，不受写入影响）
        assert result["schema"]["match"] is True, result["schema"]
        assert result["schema"]["restored_tables"] > 300

        assert set(result["checks"]) == set(backup_service.VERIFY_TABLES)
        for table, check in result["checks"].items():
            # 源库非空 → 恢复库必须也非空（dump 确实带了数据，而非只有 schema）
            assert check["complete"] is True, f"{table} 恢复后为空: {check}"
            # 恢复库不可能比源库"更新"
            assert check["consistent"] is True, f"{table} 恢复行数超过源库: {check}"
            assert check["restored"] <= check["source"]
            assert check["drift"] == check["source"] - check["restored"]
            if check["source"] > 0:
                assert check["restored"] > 0, f"{table}: {check}"

        # 临时库必须被删掉（否则每周演练会残留占盘）
        assert backup_service._count_rows(settings, "users", verify_db) == -1


@needs_pg_client
def test_base_backup_produces_base_and_wal_tarballs(tmp_path):
    """物理基础备份必须同时产出 base.tar.gz 与 pg_wal.tar.gz —— 缺 WAL 的基线无法用于 PITR。"""
    import tarfile

    with settings_override(BACKUP_DIR=str(tmp_path / "backups")):
        result = backup_service.run_base_backup()

    dest = Path(result["path"])
    base_tar = dest / "base.tar.gz"
    wal_tar = dest / "pg_wal.tar.gz"
    assert base_tar.is_file() and base_tar.stat().st_size > 0
    assert wal_tar.is_file() and wal_tar.stat().st_size > 0
    assert result["mode"] in ("local", "docker")

    with tarfile.open(base_tar) as tar:
        names = tar.getnames()
    # backup_label 是 PITR 恢复的必需文件，缺失说明不是合法的物理基线
    assert "backup_label" in names
    assert "global" in names


@needs_pg_client
def test_verify_archive_rejects_corrupt_dump(tmp_path):
    """损坏的 dump 必须被判为不可用（否则会带着坏备份上线）。"""
    bad = tmp_path / "full_19700101.dump"
    bad.write_bytes(b"this is definitely not a pg_dump custom-format archive")

    with pytest.raises(BackupError, match="pg_restore --list 失败"):
        backup_service.verify_archive(bad)

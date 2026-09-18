"""备份与灾难恢复服务（G05 · P1-1）。

对齐 Reference_guide_v0.3.md P1-1：
1. PostgreSQL 每日全量 ``pg_dump -Fc``，保留 30 天；
2. WAL 归档（``archive_mode``/``archive_command``）状态检查，支持 PITR；
3. 文件备份：``data/memory/``（人类可读记忆文件）、导出目录，保留 7 天
   （泳道 C 的 G31 已下线 Chroma，向量统一存 PG 并随 ``pg_dump`` 备份，故不再镜像 ``data/chroma/``）；
4. 异地备份：rclone 同步到对象存储，凭据走环境变量，未配置时进入模拟模式；
5. 每周恢复到临时库验证备份完整性；
6. 监控：备份成功/失败状态、备份文件大小、备份目录磁盘剩余空间。

产物布局（``BACKUP_DIR`` 下）::

    pg/full/full_YYYYMMDD.dump     逻辑全量备份（pg_dump -Fc 自定义格式，可并行恢复 / 单表恢复）
    pg/base/base_YYYYMMDD/         物理基础备份（pg_basebackup -Ft -z，PITR 的基线）
    pg/wal/                        WAL 归档（由 db 容器 archive_command 写入，本服务只检查）
    files/YYYYMMDD/<name>/         文件镜像（memory / exports）
    manifests/backup_<ts>.json     每次运行清单（大小/sha256/耗时/各步骤结果）
    status.json                    最近一次运行状态（/metrics 与告警读取）

pg_dump 取用方式（``BACKUP_PG_DUMP_MODE``）：

- ``local``  —— 直接调用 PATH 上的 pg_dump（容器内已装 postgresql-client-16）；
- ``docker`` —— 经 ``docker exec -i <容器> pg_dump``（宿主开发环境本机无 PG 客户端）；
- ``auto``   —— 默认，先探测本地 pg_dump，找不到退回 docker。

**版本约束**：pg_dump 客户端主版本必须 ≥ 服务端主版本，否则 pg_dump 拒绝执行
（本项目服务端 PG16，Debian bookworm 自带的 client-15 不可用，镜像内装 client-16）。
``check_client_version()`` 在每次备份前做该校验，版本不匹配直接失败而非产出坏备份。

CLI（供 ``scripts/backup_pg.sh`` / ``scripts/verify_backup.sh`` 与 Celery 任务调用）::

    python -m app.services.backup_service full     # 全量备份 + 清理 + 文件备份 + 异地同步
    python -m app.services.backup_service dump     # 仅 PostgreSQL 逻辑全量（pg_dump）
    python -m app.services.backup_service base     # 仅物理基础备份（pg_basebackup，PITR 基线）
    python -m app.services.backup_service files    # 仅文件镜像
    python -m app.services.backup_service offsite  # 仅异地同步
    python -m app.services.backup_service verify   # 恢复到临时库验证
    python -m app.services.backup_service prune    # 仅按保留期清理
    python -m app.services.backup_service status   # 打印最近一次状态
"""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings
from app.utils.db import engine

logger = logging.getLogger(__name__)
_settings = get_settings()

# 子进程超时（秒）：pg_dump 对分区表可能数十秒至数分钟，给足余量；卡死则中止而非挂起 worker
PG_DUMP_TIMEOUT = 3600
PG_CLIENT_TIMEOUT = 1800
FILE_SYNC_TIMEOUT = 1800
RCLONE_TIMEOUT = 3600

# 恢复演练抽样比对的表（覆盖 用户/目录/行情分区 三类关键数据）
VERIFY_TABLES = ("users", "symbols", "kline_1d")


class BackupError(RuntimeError):
    """备份链路可预期错误（缺客户端 / 版本不匹配 / 无可用备份 / 外部命令失败）。"""


# --------------------------------------------------------------------------- #
# 路径与工具
# --------------------------------------------------------------------------- #
def backup_root(settings: Settings | None = None) -> Path:
    """备份根目录（不存在则创建）。"""
    path = Path((settings or _settings).BACKUP_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dir_stats(path: Path) -> tuple[int, int]:
    """递归统计目录下 (文件数, 总字节)。"""
    files = 0
    size = 0
    for item in path.rglob("*"):
        if item.is_file():
            files += 1
            size += item.stat().st_size
    return files, size


def _db_url(settings: Settings):
    return make_url(settings.DATABASE_URL)


def _run(cmd: list[str], *, timeout: int, stdin_path: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """执行外部命令（捕获输出为文本）。stdin_path 非空时把文件内容喂给子进程标准输入。"""
    # stdin_path 为文件时喂给子进程；否则显式 DEVNULL（继承父进程 stdin 会让 docker exec -i 挂住）
    stdin_fh = open(stdin_path, "rb") if stdin_path is not None else subprocess.DEVNULL
    try:
        return subprocess.run(
            cmd,
            stdin=stdin_fh,
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    finally:
        if stdin_path is not None:
            stdin_fh.close()


def _decode(raw: bytes | None) -> str:
    return (raw or b"").decode("utf-8", errors="replace").strip()


# --------------------------------------------------------------------------- #
# pg 客户端定位（local / docker）
# --------------------------------------------------------------------------- #
def resolve_pg_client(settings: Settings | None = None, tool: str = "pg_dump") -> tuple[list[str], str]:
    """解析 pg 客户端命令前缀。

    返回 ``(argv_prefix, mode)``：local 为 ``[pg_dump 路径]``，docker 为
    ``["docker", "exec", "-i", 容器名, tool]``。两模式均以 stdin/stdout 传数据，
    故调用方无需关心产物落在容器还是宿主。
    """
    s = settings or _settings
    mode = (s.BACKUP_PG_DUMP_MODE or "auto").strip().lower()
    if mode not in ("auto", "local", "docker"):
        raise BackupError(f"未知的 BACKUP_PG_DUMP_MODE：{mode}（可选 auto/local/docker）")

    if mode in ("auto", "local"):
        binary = shutil.which(s.BACKUP_PG_DUMP_BIN) or (
            s.BACKUP_PG_DUMP_BIN if Path(s.BACKUP_PG_DUMP_BIN).is_file() else None
        )
        if binary:
            return [binary], "local"
        if mode == "local":
            raise BackupError(f"BACKUP_PG_DUMP_MODE=local 但找不到可执行文件：{s.BACKUP_PG_DUMP_BIN}")

    # docker 模式，或 auto 模式在本机找不到客户端（宿主开发环境的常见情形）
    if not shutil.which("docker"):
        raise BackupError(
            f"找不到 {tool}：请安装 postgresql-client 或设 BACKUP_PG_DUMP_MODE=docker（本机也没有 docker）"
        )
    return ["docker", "exec", "-i", s.BACKUP_PG_CONTAINER, tool], "docker"


def check_client_version(settings: Settings | None = None) -> dict:
    """校验 pg_dump 客户端主版本 ≥ 服务端主版本（不匹配时 pg_dump 会拒绝执行）。"""
    s = settings or _settings
    argv, mode = resolve_pg_client(s, "pg_dump")
    proc = _run(argv + ["--version"], timeout=60)
    if proc.returncode != 0:
        raise BackupError(f"pg_dump --version 失败：{_decode(proc.stderr)}")
    match = re.search(r"(\d+)\.", _decode(proc.stdout))
    if not match:
        raise BackupError(f"无法解析 pg_dump 版本：{_decode(proc.stdout)}")
    client_major = int(match.group(1))
    with engine.connect() as conn:
        server_version = conn.execute(text("SHOW server_version")).scalar_one()
    server_major = int(str(server_version).split(".")[0])
    if client_major < server_major:
        raise BackupError(
            f"pg_dump 客户端主版本 {client_major} < 服务端 {server_major}，"
            f"pg_dump 会拒绝执行；请在镜像内安装 postgresql-client-{server_major}"
        )
    return {"mode": mode, "client_major": client_major, "server_major": server_major, "server_version": server_version}


def _local_env(settings: Settings) -> dict:
    """local 模式连接环境：密码经 PGPASSWORD 传递，不落命令行（避免 ps 泄露）。"""
    env = dict(os.environ)
    password = _db_url(settings).password
    if password:
        env["PGPASSWORD"] = password
    return env


# --------------------------------------------------------------------------- #
# PostgreSQL 全量备份
# --------------------------------------------------------------------------- #
def run_pg_dump(settings: Settings | None = None) -> dict:
    """执行一次 pg_dump 全量备份，返回清单条目。

    先写 ``*.part`` 再原子改名 —— 中断的备份不会以合法文件名存在，避免清理/验证误判。
    """
    s = settings or _settings
    version = check_client_version(s)
    url = _db_url(s)
    argv, mode = resolve_pg_client(s, "pg_dump")

    out_dir = backup_root(s) / "pg" / "full"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"full_{_utcnow().strftime('%Y%m%d')}.dump"
    partial = target.with_name(target.name + ".part")

    args = ["-U", url.username or "postgres", "-Fc", "--no-owner", "--no-privileges"]
    if mode == "local":  # docker 模式走容器内本地 socket，无需 host/port
        if url.host:
            args += ["-h", url.host]
        if url.port:
            args += ["-p", str(url.port)]
    args.append(url.database or "stock_invest")

    started = time.monotonic()
    with open(partial, "wb") as fh:
        proc = subprocess.run(
            argv + args,
            stdin=subprocess.DEVNULL,
            stdout=fh,
            stderr=subprocess.PIPE,
            timeout=PG_DUMP_TIMEOUT,
            env=_local_env(s) if mode == "local" else None,
            check=False,
        )
    duration = round(time.monotonic() - started, 2)
    if proc.returncode != 0 or not partial.exists() or partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        raise BackupError(f"pg_dump 失败（exit={proc.returncode}）：{_decode(proc.stderr)}")

    partial.replace(target)
    entry = {
        "file": target.name,
        "path": str(target),
        "size_bytes": target.stat().st_size,
        "sha256": _sha256(target),
        "duration_s": duration,
        "mode": mode,
        "client_major": version["client_major"],
        "server_version": version["server_version"],
        "created_at": _utcnow().isoformat(),
    }
    logger.info("pg_dump ok: %s (%.1f MB, %.2fs)", target.name, entry["size_bytes"] / 1024 / 1024, duration)
    return entry


def run_base_backup(settings: Settings | None = None) -> dict:
    """物理基础备份（``pg_basebackup``），与 WAL 归档配合才能真正做 PITR。

    **为什么必须有它**：``pg_dump`` 是**逻辑**备份，只能恢复到"备份那一刻"，无法与 WAL 归档
    组合推到任意时间点 —— PITR 要求物理基础备份 + 其后的 WAL 连续归档。两者互补，都保留：

    - 逻辑备份（每日，``run_pg_dump``）：可单表恢复、跨大版本恢复、体积小、恢复快；
    - 物理备份（每周，本函数）：PITR 的唯一合法基线，配合 ``pg/wal/`` 归档可回溯到任意时刻。

    产物为 ``pg/base/base_YYYYMMDD/{base.tar.gz,pg_wal.tar.gz}``（tar + gzip，含 -X fetch 的 WAL）。
    """
    s = settings or _settings
    url = _db_url(s)
    user = url.username or "postgres"
    argv, mode = resolve_pg_client(s, "pg_basebackup")

    out_dir = backup_root(s) / "pg" / "base"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"base_{_utcnow().strftime('%Y%m%d')}"
    if dest.exists():  # 上次中断的残留，先清掉避免 pg_basebackup 拒绝写入非空目录
        shutil.rmtree(dest)

    # -Ft tar + -z 压缩 + -X stream 并发流式收 WAL + -c fast 立即 checkpoint。
    # 用 stream 而非 fetch：fetch 在备份窗口内未发生 WAL 段切换时不产出 pg_wal.tar.gz，
    # 得到的基线无法可靠用于 PITR；stream 始终把备份期间的 WAL 一并写入。
    flags = ["-Ft", "-z", "-X", "stream", "-c", "fast"]
    started = time.monotonic()
    if mode == "docker":
        # 容器内落盘 → docker cp 取回 → 删容器内临时目录
        # （不用 `-D -` 流式到 stdout：tar 格式会产生 base.tar.gz/pg_wal.tar.gz 两个成员，串流后无法直接解压）
        container = s.BACKUP_PG_CONTAINER
        tmp_in_container = f"/tmp/pgbase_{dest.name}"
        _run(["docker", "exec", container, "rm", "-rf", tmp_in_container], timeout=60)
        proc = _run(
            ["docker", "exec", container, "pg_basebackup", "-h", "/var/run/postgresql", "-U", user, "-D", tmp_in_container, *flags],
            timeout=PG_DUMP_TIMEOUT,
        )
        if proc.returncode == 0:
            _run(["docker", "cp", f"{container}:{tmp_in_container}/.", str(dest)], timeout=PG_DUMP_TIMEOUT)
            _run(["docker", "exec", container, "rm", "-rf", tmp_in_container], timeout=60)
    else:
        args = ["-U", user]
        if url.host:
            args += ["-h", url.host]
        if url.port:
            args += ["-p", str(url.port)]
        proc = _run(argv + args + ["-D", str(dest), *flags], timeout=PG_DUMP_TIMEOUT, env=_local_env(s))
    duration = round(time.monotonic() - started, 2)

    archive = dest / "base.tar.gz"
    wal_archive = dest / "pg_wal.tar.gz"
    missing = [p.name for p in (archive, wal_archive) if not p.is_file() or p.stat().st_size == 0]
    if proc.returncode != 0 or missing:
        shutil.rmtree(dest, ignore_errors=True)
        raise BackupError(
            f"pg_basebackup 失败（exit={proc.returncode}，缺失={missing}）：{_decode(proc.stderr)}"
        )

    files, size = _dir_stats(dest)
    logger.info("pg_basebackup ok: %s (%.1f MB, %.2fs)", dest.name, size / 1024 / 1024, duration)
    return {
        "dir": dest.name,
        "path": str(dest),
        "files": files,
        "size_bytes": size,
        "base_sha256": _sha256(archive),
        "wal_sha256": _sha256(wal_archive),
        "duration_s": duration,
        "mode": mode,
        "created_at": _utcnow().isoformat(),
    }


def latest_dump(settings: Settings | None = None) -> Path | None:
    """最近一次全量备份文件（按文件名日期排序，忽略 .part 残片）。"""
    out_dir = backup_root(settings) / "pg" / "full"
    if not out_dir.is_dir():
        return None
    dumps = sorted(p for p in out_dir.glob("full_*.dump") if p.is_file())
    return dumps[-1] if dumps else None


def verify_archive(dump_path: Path, settings: Settings | None = None) -> dict:
    """校验 dump 归档可读（``pg_restore --list`` 条目数），识别截断/损坏文件。"""
    s = settings or _settings
    argv, _ = resolve_pg_client(s, "pg_restore")
    proc = _run(argv + ["--list"], timeout=PG_CLIENT_TIMEOUT, stdin_path=dump_path)
    if proc.returncode != 0:
        raise BackupError(f"pg_restore --list 失败（归档损坏？）：{_decode(proc.stderr)}")
    lines = [ln for ln in _decode(proc.stdout).splitlines() if ln and not ln.startswith(";")]
    return {"entries": len(lines), "ok": len(lines) > 0}


# --------------------------------------------------------------------------- #
# 保留期清理
# --------------------------------------------------------------------------- #
def prune_dir(directory: Path, retain_days: int) -> list[str]:
    """删除 directory 下修改时间早于 retain_days 天的条目（文件或目录），返回被删名称。"""
    if retain_days <= 0 or not directory.is_dir():
        return []
    cutoff = _utcnow().timestamp() - retain_days * 86400
    removed: list[str] = []
    for item in sorted(directory.iterdir()):
        try:
            if item.stat().st_mtime >= cutoff:
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            removed.append(item.name)
        except OSError as e:  # 单个条目失败不阻断整体清理
            logger.warning("prune %s failed: %s", item, e)
    return removed


def prune_backups(settings: Settings | None = None) -> dict:
    """按配置保留期清理全量备份 / WAL 归档 / 文件镜像 / 清单。"""
    s = settings or _settings
    root = backup_root(s)
    return {
        "full": prune_dir(root / "pg" / "full", s.BACKUP_PG_RETAIN_DAYS),
        "base": prune_dir(root / "pg" / "base", s.BACKUP_BASE_RETAIN_DAYS),
        "wal": prune_dir(root / "pg" / "wal", s.BACKUP_WAL_RETAIN_DAYS),
        "files": prune_dir(root / "files", s.BACKUP_FILES_RETAIN_DAYS),
        "manifests": prune_dir(root / "manifests", s.BACKUP_PG_RETAIN_DAYS),
    }


# --------------------------------------------------------------------------- #
# 文件备份
# --------------------------------------------------------------------------- #
def file_sources(settings: Settings | None = None) -> list[tuple[str, Path]]:
    """待备份的文件目录：(名称, 路径)。

    G31 起 Chroma 已下线（向量存 memory_chunks），文件备份只含记忆文件与导出目录；
    记忆向量由 PG 逻辑备份（pg_dump）覆盖，无需单独镜像。
    """
    s = settings or _settings
    return [("memory", Path(s.MEMORY_DIR)), ("exports", Path(s.EXPORT_DIR))]


def backup_files(settings: Settings | None = None) -> dict:
    """把记忆/导出目录镜像到 ``files/YYYYMMDD/``（有 rsync 用 rsync，否则 Python 复制）。"""
    s = settings or _settings
    day = _utcnow().strftime("%Y%m%d")
    dest_root = backup_root(s) / "files" / day
    rsync = shutil.which("rsync")
    results: list[dict] = []
    for name, src in file_sources(s):
        if not src.is_dir():
            results.append({"name": name, "src": str(src), "skipped": "源目录不存在"})
            continue
        dst = dest_root / name
        dst.mkdir(parents=True, exist_ok=True)
        try:
            if rsync:
                # -a 保留属性；--delete 使镜像与源一致（源删除的文件在镜像中一并移除）
                proc = _run([rsync, "-a", "--delete", f"{src}{os.sep}", f"{dst}{os.sep}"], timeout=FILE_SYNC_TIMEOUT)
                if proc.returncode != 0:
                    results.append({"name": name, "src": str(src), "error": _decode(proc.stderr)})
                    continue
                tool = "rsync"
            else:
                shutil.copytree(src, dst, dirs_exist_ok=True)
                tool = "python-copy"
            files, size = _dir_stats(dst)
            results.append({"name": name, "src": str(src), "dst": str(dst), "files": files, "size_bytes": size, "tool": tool})
        except (OSError, subprocess.SubprocessError) as e:
            logger.warning("file backup %s failed: %s", name, e)
            results.append({"name": name, "src": str(src), "error": f"{type(e).__name__}: {e}"})
    return {"day": day, "dest": str(dest_root), "sources": results}


# --------------------------------------------------------------------------- #
# 异地备份（rclone）
# --------------------------------------------------------------------------- #
def sync_offsite(settings: Settings | None = None) -> dict:
    """rclone 同步备份目录到对象存储，并删除远端超过保留期的文件。

    ``RCLONE_REMOTE`` 未配置时进入**模拟模式**：只记录清单、不真同步（与 SMTP 模拟模式同约定）。
    凭据一律走环境变量（``RCLONE_CONFIG_*`` / ``AWS_*``），本服务不读写任何密钥。
    """
    s = settings or _settings
    remote = (s.RCLONE_REMOTE or "").strip()
    if not remote:
        logger.warning("[SIMULATED] RCLONE_REMOTE 未配置，异地备份跳过（仅记录清单）")
        return {"mode": "simulated", "remote": "", "synced": False, "retain_days": s.BACKUP_OFFSITE_RETAIN_DAYS}

    binary = shutil.which(s.RCLONE_BIN) or (s.RCLONE_BIN if Path(s.RCLONE_BIN).is_file() else None)
    if not binary:
        return {"mode": "failed", "remote": remote, "synced": False, "error": f"找不到 rclone：{s.RCLONE_BIN}"}

    base = [binary]
    if s.RCLONE_CONFIG:
        base += ["--config", s.RCLONE_CONFIG]
    started = time.monotonic()
    up = _run(base + ["sync", str(backup_root(s)), remote, "--stats-one-line", "-v"], timeout=RCLONE_TIMEOUT)
    if up.returncode != 0:
        return {"mode": "failed", "remote": remote, "synced": False, "error": _decode(up.stderr)}
    # 保留期：rclone 无 retention 参数，用 delete --min-age 删除远端过期对象
    old = _run(base + ["delete", remote, "--min-age", f"{s.BACKUP_OFFSITE_RETAIN_DAYS}d"], timeout=RCLONE_TIMEOUT)
    return {
        "mode": "rclone",
        "remote": remote,
        "synced": True,
        "retain_days": s.BACKUP_OFFSITE_RETAIN_DAYS,
        "duration_s": round(time.monotonic() - started, 2),
        "delete_ok": old.returncode == 0,
        "delete_error": _decode(old.stderr) if old.returncode != 0 else "",
    }


# --------------------------------------------------------------------------- #
# 恢复演练（每周验证备份完整性）
# --------------------------------------------------------------------------- #
def _maintenance_psql(settings: Settings, sql: str) -> dict:
    """在维护库（postgres）上执行一条 SQL（建/删临时库用）。"""
    url = _db_url(settings)
    argv, mode = resolve_pg_client(settings, "psql")
    args = ["-U", url.username or "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1", "-c", sql]
    if mode == "local":
        if url.host:
            args += ["-h", url.host]
        if url.port:
            args += ["-p", str(url.port)]
    proc = _run(argv + args, timeout=PG_CLIENT_TIMEOUT, env=_local_env(settings) if mode == "local" else None)
    if proc.returncode != 0:
        raise BackupError(f"psql 执行失败（{sql}）：{_decode(proc.stderr)}")
    return {"ok": True}


def _count_rows(settings: Settings, table: str, database: str) -> int:
    """统计指定库某表行数（表不存在返回 -1）。"""
    url = _db_url(settings)
    argv, mode = resolve_pg_client(settings, "psql")
    sql = f"SELECT count(*) FROM {table}"
    args = ["-U", url.username or "postgres", "-d", database, "-tAc", sql]
    if mode == "local":
        if url.host:
            args += ["-h", url.host]
        if url.port:
            args += ["-p", str(url.port)]
    proc = _run(argv + args, timeout=PG_CLIENT_TIMEOUT, env=_local_env(settings) if mode == "local" else None)
    if proc.returncode != 0:
        return -1
    try:
        return int(_decode(proc.stdout).splitlines()[-1])
    except (ValueError, IndexError):
        return -1


def _count_tables(settings: Settings, database: str) -> int:
    """统计库内 public schema 表数（校验恢复后 schema 完整）。"""
    url = _db_url(settings)
    argv, mode = resolve_pg_client(settings, "psql")
    sql = "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
    args = ["-U", url.username or "postgres", "-d", database, "-tAc", sql]
    if mode == "local":
        if url.host:
            args += ["-h", url.host]
        if url.port:
            args += ["-p", str(url.port)]
    proc = _run(argv + args, timeout=PG_CLIENT_TIMEOUT, env=_local_env(settings) if mode == "local" else None)
    if proc.returncode != 0:
        return -1
    try:
        return int(_decode(proc.stdout).splitlines()[-1])
    except (ValueError, IndexError):
        return -1


def verify_restore(settings: Settings | None = None, dump_path: Path | None = None) -> dict:
    """把全量备份恢复到临时库，校验其可恢复且完整，然后删除临时库（每周演练 / 发布前校验）。

    步骤：归档可读性 → 建临时库 → pg_restore → 校验 → 删临时库。
    任一步失败均清理临时库，避免残留占用磁盘。

    **校验口径（重要，勿改成"源库行数 == 恢复库行数"）**：备份代表的是 *dump 那一刻* 的状态，
    而源库是活的——dump 与比对之间发生的任何写入都会让两边行数不等，那种断言在生产每周演练里
    会**误报**（凌晨三点假告警）。因此这里只断言对任意时刻都成立的**不变式**：

    1. ``pg_restore`` 退出码 0 且无 ``pg_restore: error`` 行（dump 结构完好、可恢复）；
    2. 归档可读且条目数 > 0（未被截断）；
    3. 恢复库 public schema 表数与源库**一致**（schema 完整；表只在迁移时变化，不受写入影响）；
    4. 每张抽样表 ``restored <= source``（恢复库不可能比源库"更新"——超出即为异常）；
    5. 源库非空时 ``restored > 0``（dump 确实带了数据，而非只有 schema）。

    ``drift``（source - restored）为**信息项**：活库上 > 0 属正常（dump 之后的写入），
    若需精确相等，请先停写入方再执行本函数，届时 drift 应为 0。
    """
    s = settings or _settings
    dump = Path(dump_path) if dump_path else latest_dump(s)
    if dump is None or not dump.is_file():
        raise BackupError("没有可验证的全量备份文件（先执行 full）")

    archive = verify_archive(dump, s)
    url = _db_url(s)
    source_db = url.database or "stock_invest"
    dbname = s.BACKUP_VERIFY_DB
    argv, mode = resolve_pg_client(s, "pg_restore")

    _maintenance_psql(s, f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')
    _maintenance_psql(s, f'CREATE DATABASE "{dbname}"')
    try:
        args = ["-U", url.username or "postgres", "-d", dbname, "--no-owner", "--no-privileges"]
        if mode == "local":
            if url.host:
                args += ["-h", url.host]
            if url.port:
                args += ["-p", str(url.port)]
        started = time.monotonic()
        proc = _run(argv + args, timeout=PG_CLIENT_TIMEOUT, stdin_path=dump, env=_local_env(s) if mode == "local" else None)
        duration = round(time.monotonic() - started, 2)
        stderr = _decode(proc.stderr)
        errors = [ln for ln in stderr.splitlines() if ln.lower().startswith("pg_restore: error")]

        checks = {}
        for table in VERIFY_TABLES:
            source_rows = _count_rows(s, table, source_db)
            restored_rows = _count_rows(s, table, dbname)
            checks[table] = {
                "source": source_rows,
                "restored": restored_rows,
                "drift": (source_rows - restored_rows) if source_rows >= 0 and restored_rows >= 0 else None,
                "consistent": restored_rows >= 0 and source_rows >= 0 and restored_rows <= source_rows,
                "complete": restored_rows > 0 or source_rows <= 0,
            }
        schema = {
            "source_tables": _count_tables(s, source_db),
            "restored_tables": _count_tables(s, dbname),
        }
        schema["match"] = schema["source_tables"] > 0 and schema["source_tables"] == schema["restored_tables"]
    finally:
        _maintenance_psql(s, f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)')

    ok = (
        proc.returncode == 0
        and not errors
        and archive["ok"]
        and schema["match"]
        and all(c["consistent"] and c["complete"] for c in checks.values())
    )
    result = {
        "ok": ok,
        "dump": str(dump),
        "archive_entries": archive["entries"],
        "restore_exit": proc.returncode,
        "restore_errors": errors[:10],
        "duration_s": duration,
        "schema": schema,
        "checks": checks,
        "verified_at": _utcnow().isoformat(),
    }
    if not ok:
        logger.error("verify_restore failed: %s", json.dumps(result, ensure_ascii=False))
    else:
        logger.info(
            "verify_restore ok: %s (%.2fs, %s entries, %s tables)", dump.name, duration, archive["entries"], schema["restored_tables"]
        )
    return result


# --------------------------------------------------------------------------- #
# WAL 归档 / 磁盘 / 状态
# --------------------------------------------------------------------------- #
def archive_status(settings: Settings | None = None) -> dict:
    """WAL 归档状态：服务端 archive_mode/archive_command/wal_level + 归档目录文件数。"""
    s = settings or _settings
    info: dict = {"archive_dir": s.PG_ARCHIVE_DIR or "", "wal_files": None}
    try:
        with engine.connect() as conn:
            info["archive_mode"] = conn.execute(text("SHOW archive_mode")).scalar_one()
            info["archive_command"] = conn.execute(text("SHOW archive_command")).scalar_one()
            info["wal_level"] = conn.execute(text("SHOW wal_level")).scalar_one()
        info["enabled"] = str(info["archive_mode"]).lower() == "on"
    except Exception as e:  # noqa: BLE001 —— 归档状态查询失败不应中断备份主流程
        info["enabled"] = False
        info["error"] = f"{type(e).__name__}: {e}"
    if s.PG_ARCHIVE_DIR:
        archive_dir = Path(s.PG_ARCHIVE_DIR)
        if archive_dir.is_dir():
            info["wal_files"] = len(list(archive_dir.glob("*")))
    return info


def disk_usage(settings: Settings | None = None) -> dict:
    """备份目录所在文件系统用量（磁盘剩余不足将导致备份写坏，需提前告警）。"""
    s = settings or _settings
    root = backup_root(s)
    total, used, free = shutil.disk_usage(root)
    free_pct = round(free / total * 100, 2) if total else 0.0
    return {
        "path": str(root),
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "free_pct": free_pct,
        "low": free_pct < s.BACKUP_DISK_MIN_FREE_PCT,
        "min_free_pct": s.BACKUP_DISK_MIN_FREE_PCT,
    }


def write_status(status: dict, settings: Settings | None = None) -> Path:
    """把最近一次运行状态落盘（``status.json``），供 /metrics 与告警读取。"""
    path = backup_root(settings) / "status.json"
    tmp = path.with_name("status.json.tmp")
    tmp.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def backup_status(settings: Settings | None = None) -> dict:
    """读取最近一次备份状态并派生过期判定（供监控/CLI status 使用）。"""
    s = settings or _settings
    path = Path(s.BACKUP_DIR) / "status.json"
    if not path.is_file():
        return {"ok": False, "reason": "no_status", "path": str(path)}
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"ok": False, "reason": "unreadable", "path": str(path), "error": str(e)}
    finished = status.get("finished_at")
    age_hours = None
    if finished:
        try:
            age_hours = round((_utcnow() - datetime.fromisoformat(finished)).total_seconds() / 3600, 2)
        except ValueError:
            age_hours = None
    status["age_hours"] = age_hours
    status["stale"] = age_hours is None or age_hours > s.BACKUP_MAX_AGE_HOURS
    return status


# --------------------------------------------------------------------------- #
# 编排入口
# --------------------------------------------------------------------------- #
def run_full_backup(settings: Settings | None = None) -> dict:
    """每日全量备份编排：pg_dump → 归档校验 → 清理 → 文件镜像 → 异地同步 → 落盘状态。

    各步骤独立捕获异常：单步失败不阻断后续（磁盘/状态仍要落盘以便告警），
    最终 ``ok`` 取决于 pg_dump 是否成功（备份主目标）。
    """
    s = settings or _settings
    started = _utcnow()
    result: dict = {"started_at": started.isoformat(), "steps": {}}

    if not s.BACKUP_ENABLED:
        result.update({"ok": True, "skipped": "BACKUP_ENABLED=false", "finished_at": _utcnow().isoformat()})
        return result

    for name, fn in (
        ("pg_dump", run_pg_dump),
        ("files", backup_files),
        ("prune", prune_backups),
        ("offsite", sync_offsite),
    ):
        try:
            result["steps"][name] = fn(s)
        except Exception as e:  # noqa: BLE001 —— 记录失败原因后继续，保证状态可观测
            logger.exception("backup step %s failed", name)
            result["steps"][name] = {"error": f"{type(e).__name__}: {e}"}

    dump_step = result["steps"].get("pg_dump", {})
    if "path" in dump_step:
        try:
            result["steps"]["archive_check"] = verify_archive(Path(dump_step["path"]), s)
        except Exception as e:  # noqa: BLE001
            result["steps"]["archive_check"] = {"error": f"{type(e).__name__}: {e}"}

    try:
        result["archive"] = archive_status(s)
        result["disk"] = disk_usage(s)
    except Exception as e:  # noqa: BLE001
        result["disk"] = {"error": f"{type(e).__name__}: {e}"}

    # 备份主目标是 pg_dump；归档可读性校验失败同样视为本次备份不可信
    archive_check = result["steps"].get("archive_check")
    result["ok"] = "path" in dump_step and bool(archive_check) and "error" not in archive_check
    result["finished_at"] = _utcnow().isoformat()
    result["duration_s"] = round((_utcnow() - started).total_seconds(), 2)

    manifest_dir = backup_root(s) / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = manifest_dir / f"backup_{started.strftime('%Y%m%dT%H%M%S')}.json"
    manifest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["manifest"] = str(manifest)
    write_status(result, s)
    return result


def run_cli(argv: list[str] | None = None) -> int:
    """命令行入口（供 scripts/*.sh 与 Celery 任务调用），返回进程退出码。"""
    # Windows 控制台默认 cp936，中文日志/JSON 会乱码；容器内为 UTF-8 无影响
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    command = (argv if argv is not None else sys.argv[1:]) or ["full"]
    action = command[0]
    handlers = {
        "full": run_full_backup,
        "dump": run_pg_dump,
        "base": run_base_backup,
        "files": backup_files,
        "offsite": sync_offsite,
        "verify": verify_restore,
        "status": backup_status,
        "prune": prune_backups,
    }
    if action not in handlers:
        print(f"unknown command: {action}（可选 {'/'.join(handlers)}）", file=sys.stderr)
        return 2
    try:
        result = handlers[action]()
    except BackupError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(run_cli())

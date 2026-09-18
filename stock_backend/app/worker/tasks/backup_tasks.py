"""备份队列任务（G05 · P1-1）：每日全量备份 / 每日异地同步 / 每周恢复演练。

调度时刻（见 app/worker/beat.py）刻意选在业务空闲窗口：02:00 全量、02:30 异地同步、
周日 03:30 恢复演练 —— worker 当前为 ``--pool=solo --concurrency=1``，备份执行期间会独占
worker，放凌晨可避免阻塞 15s 实时轮询（realtime_poll 在非交易时段本就空转返回）。

实现说明：任务直接调用 ``backup_service``（与 ``scripts/backup_pg.sh`` 同一实现），
不通过 shell 转发 —— worker 在 Windows 宿主与 Linux 容器均需可跑，依赖 bash 会引入平台差异。
脚本保留给人工执行 / 系统 cron / 容器内独立调用。

队列：``backup``（独立队列，便于后续按队列扩 worker 实例时与 sync/ai 隔离）。
"""

import logging

from app.core.request_id import get_request_id
from app.services import backup_service
from app.utils.db import get_session
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _log(task_type: str, task_id: str, status: str, message: str) -> None:
    from app.repositories import ops_repo

    db = get_session()
    try:
        ops_repo.log_task(db, task_type, task_id, status, message, request_id=get_request_id())
        db.commit()
    finally:
        db.close()


def _summary(result: dict) -> str:
    """从备份结果里提炼一行可读摘要（写 task_logs，便于排障时直接看日志表）。"""
    dump = result.get("steps", {}).get("pg_dump", {})
    parts = [f"ok={result.get('ok')}"]
    if "file" in dump:
        parts.append(f"{dump['file']}={dump['size_bytes'] / 1024 / 1024:.1f}MB")
        parts.append(f"mode={dump.get('mode')}")
    else:
        parts.append(f"pg_dump_error={dump.get('error', 'unknown')}")
    failed = [name for name, step in result.get("steps", {}).items() if isinstance(step, dict) and "error" in step]
    if failed:
        parts.append("failed_steps=" + ",".join(failed))
    disk = result.get("disk", {})
    if "free_pct" in disk:
        parts.append(f"disk_free={disk['free_pct']}%")
    return " ".join(parts)


@celery_app.task(bind=True, name="app.worker.tasks.backup_tasks.backup_daily")
def backup_daily(self) -> dict:
    """每日全量备份（beat 02:00）：pg_dump + 归档校验 + 清理 + 文件镜像 + 异地同步。"""
    _log("backup", self.request.id, "running", "start daily backup")
    result = backup_service.run_full_backup()
    status = "success" if result.get("ok") else "failed"
    message = _summary(result)
    _log("backup", self.request.id, status, message)
    if not result.get("ok"):
        # 抛出而非静默返回：Celery 标记 FAILURE，配合 Prometheus 告警/日志检索触发人工介入
        raise RuntimeError(f"daily backup failed: {message}")
    logger.info("daily backup done: %s", message)
    return {"ok": True, "summary": message, "manifest": result.get("manifest")}


@celery_app.task(bind=True, name="app.worker.tasks.backup_tasks.backup_base_weekly")
def backup_base_weekly(self) -> dict:
    """每周物理基础备份（beat 周日 02:45）：pg_basebackup，PITR 的唯一合法基线。

    没有它，``pg/wal/`` 里归档的 WAL 无法被用于时间点恢复（pg_dump 是逻辑备份，
    只能恢复到备份那一刻）。与 WAL 保留 7 天配合，提供 7 天 PITR 可回溯窗口。
    """
    _log("backup_base", self.request.id, "running", "start physical base backup")
    try:
        result = backup_service.run_base_backup()
    except Exception as e:  # noqa: BLE001 —— 统一落 task_logs 后再抛，保证失败可查
        _log("backup_base", self.request.id, "failed", f"{type(e).__name__}: {e}")
        raise
    message = f"dir={result['dir']} {result['size_bytes'] / 1024 / 1024:.1f}MB mode={result['mode']}"
    _log("backup_base", self.request.id, "success", message)
    logger.info("base backup done: %s", message)
    return result


@celery_app.task(bind=True, name="app.worker.tasks.backup_tasks.offsite_sync_daily")
def offsite_sync_daily(self) -> dict:
    """每日异地同步（beat 02:30）：rclone 同步备份目录到对象存储。

    ``RCLONE_REMOTE`` 未配置时进入模拟模式（只记清单、不算失败）——本地开发可正常跑通，
    生产部署必须配置远端与凭据，否则异地备份形同虚设（见 disaster_recovery.md 第 5 节）。
    """
    _log("backup_offsite", self.request.id, "running", "start offsite sync")
    result = backup_service.sync_offsite()
    ok = result.get("mode") != "failed"
    _log(
        "backup_offsite",
        self.request.id,
        "success" if ok else "failed",
        f"mode={result.get('mode')} remote={result.get('remote') or '(未配置)'} synced={result.get('synced')}",
    )
    if not ok:
        raise RuntimeError(f"offsite sync failed: {result.get('error')}")
    return result


@celery_app.task(bind=True, name="app.worker.tasks.backup_tasks.verify_backup_weekly")
def verify_backup_weekly(self) -> dict:
    """每周恢复演练（beat 周日 03:30）：恢复到临时库抽样比对，验证备份真的可用。"""
    _log("backup_verify", self.request.id, "running", "start restore verification")
    result = backup_service.verify_restore()
    checks = result.get("checks", {})
    detail = " ".join(f"{k}:{v['source']}→{v['restored']}" for k, v in checks.items())
    _log(
        "backup_verify",
        self.request.id,
        "success" if result.get("ok") else "failed",
        f"dump={result.get('dump')} entries={result.get('archive_entries')} {detail}",
    )
    if not result.get("ok"):
        raise RuntimeError(f"backup verification failed: {detail or result.get('restore_errors')}")
    logger.info("backup verification ok: %s", detail)
    return result

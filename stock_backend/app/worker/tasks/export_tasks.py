"""导出队列任务（G17）：用户数据导出 + 过期文件清理。

队列说明：复用 ai 队列（worker 启动命令 `-Q backtest,sync,ai` 未含独立 export 队列，
新增队列需同步改 docker-compose；放 sync 会阻塞 15s 实时轮询）。详见 Agent_code.md 待确认项。
"""

import logging

from app.core.request_id import get_request_id
from app.services import export_service
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


@celery_app.task(bind=True, name="app.worker.tasks.export_tasks.run_user_export")
def run_user_export(self, task_id: int) -> dict:
    """执行用户数据导出：打包 ZIP → 更新任务状态。"""
    _log("export", self.request.id, "running", f"start task_id={task_id}")
    db = get_session()
    try:
        from app.repositories import export_repo

        task = export_repo.get(db, task_id)
        if task is None:
            _log("export", self.request.id, "failed", f"task_id={task_id} not found")
            return {"task_id": task_id, "status": "failed", "error": "任务不存在"}
        try:
            zip_path = export_service.build_export_zip(db, task_id)
            _log("export", self.request.id, "success", f"done task_id={task_id} file={zip_path.name}")
            return {"task_id": task_id, "status": "success", "file": zip_path.name}
        except Exception as exc:  # noqa: BLE001
            logger.exception("export failed task_id=%s", task_id)
            db.rollback()
            task = export_repo.get(db, task_id)
            if task is not None:
                export_repo.update_status(db, task, "failed", error=f"{type(exc).__name__}: {exc}")
                db.commit()
            _log("export", self.request.id, "failed", f"task_id={task_id}: {exc}")
            raise
    finally:
        db.close()


@celery_app.task(name="app.worker.tasks.export_tasks.cleanup_expired_exports")
def cleanup_expired_exports() -> dict:
    """清理过期导出文件（beat 每日调度）。"""
    db = get_session()
    try:
        count = export_service.cleanup_expired_exports(db)
        if count:
            logger.info("cleanup expired exports: %s", count)
        return {"cleaned": count}
    finally:
        db.close()

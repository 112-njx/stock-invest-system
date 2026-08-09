"""回测队列任务：执行回测 → 状态机 → 结果入库（4.3）。

- 业务错误（BacktestFatalError：无K线/策略非法/超时）不重试，直接标记 failed；
- 运行时错误指数退避重试（max_retries 可配），重试前回到 queued；
- 全链路日志写 task_logs。
"""

import logging

from app.core.config import get_settings
from app.core.request_id import get_request_id
from app.services import backtest_service
from app.utils.db import get_session
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


def _log(task_type: str, task_id: str, status: str, message: str) -> None:
    from app.repositories import ops_repo

    db = get_session()
    try:
        ops_repo.log_task(db, task_type, task_id, status, message, request_id=get_request_id())
        db.commit()
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.worker.tasks.backtest_tasks.run_backtest_task",
    max_retries=settings.BACKTEST_MAX_RETRIES,
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    task_soft_time_limit=settings.BACKTEST_SOFT_TIME_LIMIT,  # 软超时（秒）
    task_time_limit=settings.BACKTEST_HARD_TIME_LIMIT,  # 硬超时（秒，策略死循环兜底，worker 被终止重启）
)
def run_backtest_task(self, task_id: int) -> dict:
    _log("backtest", self.request.id, "running", f"start task_id={task_id}")
    try:
        result = backtest_service.execute_backtest(task_id)
        _log("backtest", self.request.id, "success", f"done task_id={task_id}")
        return result
    except backtest_service.BacktestFatalError as exc:
        # 业务错误：不重试，直接失败
        logger.warning("backtest fatal task_id=%s: %s", task_id, exc)
        backtest_service.mark_task_failed(task_id, str(exc))
        _log("backtest", self.request.id, "failed", f"task_id={task_id} fatal: {exc}")
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("backtest failed task_id=%s", task_id)
        _log("backtest", self.request.id, "failed", f"task_id={task_id}: {exc}")
        if self.request.retries < self.max_retries:
            backtest_service.mark_task_queued(task_id)  # 重试前回到 queued
            raise self.retry(exc=exc) from exc
        backtest_service.mark_task_failed(task_id, f"{type(exc).__name__}: {exc}")
        raise

"""行情同步 Celery 任务：kline_init / kline_incremental / realtime_poll。

任务内只做薄编排：调用同步服务，状态与全链路日志写 sync_tasks / task_logs。
"""

import logging

from app.core.request_id import get_request_id
from app.services import sync_service
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


@celery_app.task(bind=True, name="app.worker.tasks.sync_tasks.kline_init")
def kline_init(self, symbol_id: int | None = None, days: int | None = None) -> dict:
    """首次全量历史K线（可指定标的或全部）。"""
    _log("kline_init", self.request.id, "running", f"start symbol_id={symbol_id} days={days}")
    try:
        result = sync_service.run_kline_init(symbol_id=symbol_id, days=days)
        _log("kline_init", self.request.id, "success", f"done: {result}")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("kline_init failed")
        _log("kline_init", self.request.id, "failed", str(exc))
        raise


@celery_app.task(bind=True, name="app.worker.tasks.sync_tasks.kline_incremental")
def kline_incremental(self, symbol_id: int | None = None) -> dict:
    """每日收盘后增量同步。"""
    _log("kline_incremental", self.request.id, "running", f"start symbol_id={symbol_id}")
    try:
        result = sync_service.run_kline_incremental(symbol_id=symbol_id)
        _log("kline_incremental", self.request.id, "success", f"done: {result}")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("kline_incremental failed")
        _log("kline_incremental", self.request.id, "failed", str(exc))
        raise


@celery_app.task(bind=True, name="app.worker.tasks.sync_tasks.realtime_poll")
def realtime_poll(self, symbol_id: int | None = None, force: bool = False) -> dict:
    """交易时段实时快照轮询；非交易时段跳过（beat 周期触发，force 用于手动验证/运维）。"""
    if not force and not sync_service.is_market_open():
        return {"skipped": "market closed"}
    _log("realtime", self.request.id, "running", f"start symbol_id={symbol_id}")
    try:
        result = sync_service.run_realtime_poll(symbol_id=symbol_id)
        _log("realtime", self.request.id, "success", f"done: {result}")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("realtime_poll failed")
        _log("realtime", self.request.id, "failed", str(exc))
        raise

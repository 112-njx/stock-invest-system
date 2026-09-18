"""回测域读写：backtest_tasks 状态机 + backtest_results（按 strategy 隔离）。"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer

from app.models.strategy import BacktestResult, BacktestTask


# ---- backtest_tasks ----
def create_task(
    db: Session,
    strategy_id: int,
    symbol_id: int,
    period: str = "1d",
    start_ts: datetime | None = None,
    end_ts: datetime | None = None,
    fill_on: str = "close",
) -> BacktestTask:
    row = BacktestTask(
        strategy_id=strategy_id,
        symbol_id=symbol_id,
        period=period,
        start_ts=start_ts,
        end_ts=end_ts,
        fill_on=fill_on,
        status="queued",
        progress=0,
    )
    db.add(row)
    db.flush()
    return row


def get_task(db: Session, task_id: int) -> BacktestTask | None:
    return db.get(BacktestTask, task_id)


def update_task(db: Session, task_id: int, status: str | None = None, progress: int | None = None, error: str | None = None) -> None:
    row = db.get(BacktestTask, task_id)
    if row is None:
        return
    if status is not None:
        row.status = status
    if progress is not None:
        row.progress = progress
    if error is not None:
        row.error = error
    db.flush()


def list_tasks_by_strategy(
    db: Session, strategy_id: int, offset: int | None = None, limit: int | None = None
) -> list[BacktestTask]:
    """单策略的回测任务（id 倒序）。offset/limit 为 None 时不限。"""
    stmt = select(BacktestTask).where(BacktestTask.strategy_id == strategy_id).order_by(BacktestTask.id.desc())
    if offset is not None:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))


def count_tasks_by_strategy(db: Session, strategy_id: int) -> int:
    stmt = select(func.count()).select_from(BacktestTask).where(BacktestTask.strategy_id == strategy_id)
    return int(db.scalar(stmt) or 0)


def list_tasks_by_strategies(
    db: Session, strategy_ids: list[int], offset: int | None = None, limit: int | None = None
) -> list[BacktestTask]:
    """多策略（当前用户全部策略）的回测任务（id 倒序）。"""
    if not strategy_ids:
        return []
    stmt = select(BacktestTask).where(BacktestTask.strategy_id.in_(strategy_ids)).order_by(BacktestTask.id.desc())
    if offset is not None:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))


def count_tasks_by_strategies(db: Session, strategy_ids: list[int]) -> int:
    if not strategy_ids:
        return 0
    stmt = select(func.count()).select_from(BacktestTask).where(BacktestTask.strategy_id.in_(strategy_ids))
    return int(db.scalar(stmt) or 0)


# ---- backtest_results ----
def create_result(
    db: Session,
    task_id: int,
    strategy_id: int,
    symbol_id: int,
    metrics: dict,
    start_ts: datetime | None,
    end_ts: datetime | None,
    equity_curve: list | None = None,
    trades: list | None = None,
) -> BacktestResult:
    row = BacktestResult(
        task_id=task_id,
        strategy_id=strategy_id,
        symbol_id=symbol_id,
        win_rate=metrics.get("win_rate"),
        profit_loss_ratio=metrics.get("profit_loss_ratio"),
        sharpe=metrics.get("sharpe"),
        total_buys=metrics.get("total_buys"),
        total_sells=metrics.get("total_sells"),
        annual_return=metrics.get("annual_return"),
        max_drawdown=metrics.get("max_drawdown"),
        metrics_json=metrics.get("metrics_json") or {},
        equity_curve=equity_curve,
        trades=trades,
        start_ts=start_ts,
        end_ts=end_ts,
    )
    db.add(row)
    db.flush()
    return row


def list_results_by_strategy(db: Session, strategy_id: int) -> list[BacktestResult]:
    """按策略列结果（G32：defer 大列——equity_curve/trades 单条约 60KB，列表不取）。"""
    return list(
        db.scalars(
            select(BacktestResult)
            .options(defer(BacktestResult.equity_curve), defer(BacktestResult.trades))
            .where(BacktestResult.strategy_id == strategy_id)
            .order_by(BacktestResult.id.desc())
        )
    )


def get_result(db: Session, result_id: int) -> BacktestResult | None:
    return db.get(BacktestResult, result_id)


def get_result_by_task(db: Session, task_id: int) -> BacktestResult | None:
    """按任务取结果（G12 幂等：同一任务已有结果时不再重复执行/重复落库）。"""
    return db.scalars(select(BacktestResult).where(BacktestResult.task_id == task_id).order_by(BacktestResult.id)).first()

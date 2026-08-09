"""回测域读写：backtest_tasks 状态机 + backtest_results（按 strategy 隔离）。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

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


def list_tasks_by_strategy(db: Session, strategy_id: int, limit: int = 20) -> list[BacktestTask]:
    return list(
        db.scalars(select(BacktestTask).where(BacktestTask.strategy_id == strategy_id).order_by(BacktestTask.id.desc()).limit(limit))
    )


# ---- backtest_results ----
def create_result(
    db: Session,
    task_id: int,
    strategy_id: int,
    symbol_id: int,
    metrics: dict,
    start_ts: datetime | None,
    end_ts: datetime | None,
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
        start_ts=start_ts,
        end_ts=end_ts,
    )
    db.add(row)
    db.flush()
    return row


def list_results_by_strategy(db: Session, strategy_id: int) -> list[BacktestResult]:
    return list(
        db.scalars(
            select(BacktestResult).where(BacktestResult.strategy_id == strategy_id).order_by(BacktestResult.id.desc())
        )
    )


def get_result(db: Session, result_id: int) -> BacktestResult | None:
    return db.get(BacktestResult, result_id)

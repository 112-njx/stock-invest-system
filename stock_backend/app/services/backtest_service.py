"""回测服务（4.3/4.4）：发起任务 → Celery 执行 → 结果入库 → 结果转本地记忆。

状态机 queued → running → success/failed（业务错误不重试，运行时错误由任务层重试）。
结果与任务 success 在同一事务写入（与策略保持原子）；记忆抽取 best-effort 不影响主链路。
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backtest import metrics
from app.backtest.engine import BacktestConfig, BacktestEngine, BacktestError, BacktestTimeout
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.models.kline import KLINE_MODELS
from app.models.strategy import TradingStrategy
from app.models.symbol import Symbol
from app.repositories import backtest_repo, kline_repo, strategy_repo, symbol_repo
from app.utils.db import get_session

logger = logging.getLogger(__name__)
settings = get_settings()

_KLINE_LIMIT = 50_000  # 回测 K 线拉取上限（15m 两年约 8k 根，50k 充足）
_VALID_FILL = ("close", "open")


class BacktestFatalError(Exception):
    """回测业务错误（不可重试：策略非法/标的无数据）。"""


# ---- 发起回测（API 层调用）----
def create_backtest(
    db: Session,
    user_id: int,
    strategy_id: int,
    symbol: str,
    period: str,
    start: datetime | None,
    end: datetime | None,
    fill_on: str,
) -> dict:
    if period not in KLINE_MODELS:
        raise ApiError(status_code=400, code=40030, msg=f"不支持的周期: {period}")
    if fill_on not in _VALID_FILL:
        raise ApiError(status_code=400, code=40030, msg="fill_on 仅支持 close|open")
    strategy = strategy_repo.get_strategy(db, user_id, strategy_id)
    if strategy is None:
        raise ApiError(status_code=404, code=40420, msg="策略不存在")
    symbol_id = _resolve_symbol(db, symbol)
    if symbol_id is None:
        raise ApiError(status_code=404, code=40400, msg="标的不存在")

    end = end or datetime.now(UTC)
    start = start or end - timedelta(days=settings.BACKTEST_DEFAULT_DAYS)
    task = backtest_repo.create_task(db, strategy_id, symbol_id, period, start, end, fill_on)
    db.commit()

    # 异步入队（Celery backtest 队列）；broker 不可用时任务留 queued 由运维重放
    try:
        from app.worker.tasks.backtest_tasks import run_backtest_task

        run_backtest_task.delay(task.id)
    except Exception as e:  # noqa: BLE001
        logger.warning("backtest enqueue failed task_id=%s: %s", task.id, e)
    return task


def _resolve_symbol(db: Session, symbol: str) -> int | None:
    """代码/id → symbol_id（验证存在）。"""
    from app.services.market_service import resolve_symbol_id

    sid = resolve_symbol_id(db, symbol)
    if sid is None:
        return None
    return sid if symbol_repo.get_by_id(db, sid) else None


# ---- 回测执行（Celery worker 调用）----
def execute_backtest(task_id: int) -> dict:
    db = get_session()
    try:
        task = backtest_repo.get_task(db, task_id)
        if task is None:
            raise BacktestFatalError(f"回测任务不存在: {task_id}")
        backtest_repo.update_task(db, task_id, status="running", progress=0)
        db.commit()

        strategy = db.get(TradingStrategy, task.strategy_id)
        if strategy is None or not strategy.code:
            raise BacktestFatalError("策略不存在或无策略代码")
        symbol = db.get(Symbol, task.symbol_id)
        if symbol is None:
            raise BacktestFatalError("回测标的不存在")

        bars = kline_repo.get_bars(db, task.period, task.symbol_id, task.start_ts, task.end_ts, limit=_KLINE_LIMIT)
        if not bars:
            raise BacktestFatalError("标的无 K 线数据，请先同步行情后再回测")
        bars_dict = [_bar_to_dict(b) for b in bars]

        config = BacktestConfig(
            initial_cash=settings.BACKTEST_INITIAL_CASH,
            commission_rate=settings.BACKTEST_COMMISSION_RATE,
            stamp_duty_rate=settings.BACKTEST_STAMP_DUTY_RATE,
            fill_on=task.fill_on,
            time_budget=settings.BACKTEST_TIME_BUDGET,
            period=task.period,
        )

        def _progress(pct: int) -> None:
            backtest_repo.update_task(db, task_id, progress=pct)

        out = BacktestEngine(config).run(strategy.code, strategy.params, bars_dict, progress_cb=_progress)
        m = metrics.compute_metrics(out["trades"], out["equity_curve"], out["initial_cash"], out["start_ts"], out["end_ts"], task.period)
        result = backtest_repo.create_result(db, task_id, task.strategy_id, task.symbol_id, m, out["start_ts"], out["end_ts"])
        backtest_repo.update_task(db, task_id, status="success", progress=100, error=None)
        db.commit()  # 结果 + 任务 success 原子写入

        _save_backtest_memory(db, strategy.user_id, strategy.title, symbol, result.id, m)
        return {"task_id": task_id, "result_id": result.id, "metrics": m}
    except BacktestTimeout as e:
        raise BacktestFatalError(f"回测超时: {e}") from e
    except BacktestError as e:
        raise BacktestFatalError(str(e)) from e
    finally:
        db.close()


def mark_task_failed(task_id: int, error: str) -> None:
    db = get_session()
    try:
        backtest_repo.update_task(db, task_id, status="failed", error=error[:1000])
        db.commit()
    finally:
        db.close()


def mark_task_queued(task_id: int) -> None:
    db = get_session()
    try:
        backtest_repo.update_task(db, task_id, status="queued", progress=0)
        db.commit()
    finally:
        db.close()


# ---- 查询（API 层调用，user 隔离）----
def get_task(db: Session, user_id: int, task_id: int):
    task = backtest_repo.get_task(db, task_id)
    if task is None or not _strategy_owned(db, user_id, task.strategy_id):
        raise ApiError(status_code=404, code=40430, msg="回测任务不存在")
    return task


def list_tasks(db: Session, user_id: int, strategy_id: int | None = None, limit: int = 20) -> list:
    from app.models.strategy import BacktestTask

    if strategy_id is not None:
        if not _strategy_owned(db, user_id, strategy_id):
            raise ApiError(status_code=404, code=40420, msg="策略不存在")
        return backtest_repo.list_tasks_by_strategy(db, strategy_id, limit=limit)
    # 当前用户全部策略的任务（join strategies 按 user 过滤）
    ids = [s.id for s in strategy_repo.list_strategies(db, user_id)]
    if not ids:
        return []
    return list(db.scalars(select(BacktestTask).where(BacktestTask.strategy_id.in_(ids)).order_by(BacktestTask.id.desc()).limit(limit)))


def list_results(db: Session, user_id: int, strategy_id: int) -> list:
    if not _strategy_owned(db, user_id, strategy_id):
        raise ApiError(status_code=404, code=40420, msg="策略不存在")
    return backtest_repo.list_results_by_strategy(db, strategy_id)


def get_result(db: Session, user_id: int, result_id: int):
    result = backtest_repo.get_result(db, result_id)
    if result is None or not _strategy_owned(db, user_id, result.strategy_id):
        raise ApiError(status_code=404, code=40430, msg="回测结果不存在")
    return result


def _strategy_owned(db: Session, user_id: int, strategy_id: int) -> bool:
    return strategy_repo.get_strategy(db, user_id, strategy_id) is not None


# ---- 内部 ----
def _bar_to_dict(b) -> dict:
    return {
        "ts": b.ts,
        "open": float(b.open),
        "high": float(b.high),
        "low": float(b.low),
        "close": float(b.close),
        "volume": b.volume,
        "amount": float(b.amount),
    }


def _save_backtest_memory(db: Session, user_id: int, strategy_title: str, symbol: Symbol, result_id: int, m: dict) -> None:
    """回测结果抽取转本地记忆（best-effort：记忆失败不影响回测主链路）。"""
    try:
        from app.agent.memory import memory_service

        def _rate(v):
            return f"{v * 100:.1f}%" if v is not None else "无"

        content = (
            f"策略「{strategy_title}」在{symbol.name}({symbol.code})回测结果："
            f"胜率{_rate(m.get('win_rate'))}、盈亏比{_rate(m.get('profit_loss_ratio'))}、"
            f"年化{_rate(m.get('annual_return'))}、最大回撤{_rate(m.get('max_drawdown'))}、"
            f"交易{(m.get('total_buys') or 0)}买/{(m.get('total_sells') or 0)}卖。"
        )
        memory_service.save_memory(
            db, user_id, source_type="backtest", source_id=result_id,
            facts=[{"content": content, "type": "experience", "importance": 5}],
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("save backtest memory failed user=%s result=%s: %s", user_id, result_id, e)

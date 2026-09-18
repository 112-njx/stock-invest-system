"""回测服务（4.3/4.4）：发起任务 → Celery 执行 → 结果入库 → 结果转本地记忆。

状态机 queued → running → success/failed（业务错误不重试，运行时错误由任务层重试）。
结果与任务 success 在同一事务写入（与策略保持原子）；记忆抽取 best-effort 不影响主链路。
"""

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.backtest import metrics
from app.backtest.engine import BacktestConfig, BacktestError, BacktestTimeout
from app.backtest.runner import run_isolated
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.models.kline import KLINE_MODELS
from app.models.strategy import TradingStrategy
from app.models.symbol import Symbol
from app.repositories import backtest_repo, kline_repo, strategy_repo, symbol_repo
from app.services import backtest_monitor, backtest_quota
from app.utils.db import get_session
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
settings = get_settings()

_KLINE_LIMIT = 50_000  # 回测 K 线拉取上限（15m 两年约 8k 根，50k 充足）
_VALID_FILL = ("close", "open")
_VALIDATION_CACHE_TTL = 3600  # 三级校验结果缓存秒数（按代码哈希，改代码自动失效）


# ---- 提交前三级校验（G25 · P1-4b）----
def _validate_strategy_or_raise(code: str) -> None:
    """提交回测前强制三级校验（语法 → 接口 → 沙箱 dry-run），不通过抛 400。

    G25 要求「提交回测前必须通过三级校验」。dry-run 要起子进程（CPU 1s / 内存 64MB），
    对同一份代码反复校验没有意义，故按**代码哈希**缓存结果 1h（代码一改哈希即变，自动失效）。
    Redis 不可用时退化为每次都校验（正确性不受影响，只是慢一点）。
    """
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    cache_key = f"strategy_valid:{digest}"
    result: dict | None = None
    try:
        raw = get_redis_client().get(cache_key)
        if raw:
            result = json.loads(raw)
    except Exception as e:  # noqa: BLE001 —— 缓存不可用不影响校验本身
        logger.warning("strategy validation cache read failed: %s", e)

    if result is None:
        from app.agent.strategy_validator import validate_strategy

        result = validate_strategy(code)
        try:
            get_redis_client().set(
                cache_key,
                json.dumps({"valid": result["valid"], "errors": result["errors"][:5]}, ensure_ascii=False),
                ex=_VALIDATION_CACHE_TTL,
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("strategy validation cache write failed: %s", e)

    if not result["valid"]:
        detail = "；".join(
            (f"第 {e['line']} 行：{e['message']}" if e.get("line") else str(e["message"]))
            for e in result["errors"][:3]
        )
        raise ApiError(status_code=400, code=40031, msg=f"策略校验未通过：{detail}")


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
    # G25：提交回测前强制三级校验 —— 放在配额/队列检查之前，非法策略不占用并发槽位
    _validate_strategy_or_raise(strategy.code or "")
    symbol_id = _resolve_symbol(db, symbol)
    if symbol_id is None:
        raise ApiError(status_code=404, code=40400, msg="标的不存在")

    end = end or datetime.now(UTC)
    start = start or end - timedelta(days=settings.BACKTEST_DEFAULT_DAYS)

    # G08（P1-4a）：全局队列积压 → 直接拒绝，避免任务排进去干等（全局并发由 worker 数控制）
    if backtest_quota.is_queue_busy():
        depth = backtest_quota.queue_depth()
        raise ApiError(
            status_code=429,
            code=42902,
            msg=(
                f"当前回测队列繁忙（积压 {depth} 个，预计等待约 "
                f"{backtest_quota.estimate_wait_minutes(depth)} 分钟），请稍后重试"
            ),
        )

    # G08：per-user 并发配额。用一次性 token 作槽位，避免"先建任务再占配额"失败时要回滚任务行；
    # token 随任务传给 worker，由任务在终态释放（见 backtest_tasks.run_backtest_task）。
    quota_token = uuid.uuid4().hex
    granted, running = backtest_quota.acquire(user_id, quota_token)
    if not granted:
        raise ApiError(
            status_code=429,
            code=42901,
            msg=f"同时运行的回测已达上限（{running}/{settings.BACKTEST_MAX_CONCURRENT_PER_USER}），请等待当前回测完成",
        )

    try:
        task = backtest_repo.create_task(db, strategy_id, symbol_id, period, start, end, fill_on)
        db.commit()
    except Exception:
        backtest_quota.release(user_id, quota_token)  # 建任务失败 → 立即归还配额
        raise

    # 异步入队（Celery backtest 队列）；broker 不可用时任务留 queued 由运维重放
    try:
        from app.worker.tasks.backtest_tasks import run_backtest_task

        run_backtest_task.delay(task.id, quota_token)
    except Exception as e:  # noqa: BLE001
        logger.warning("backtest enqueue failed task_id=%s: %s", task.id, e)
        # 入队失败 → 归还配额，否则用户要等 stale 阈值才能再提交
        backtest_quota.release(user_id, quota_token)
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

        # G12 幂等：任务已成功且结果已落库 → 直接返回既有结果。
        # Celery 在 worker 被强杀后会重投未 ack 的任务（at-least-once），若不做这层短路，
        # 同一 task_id 会重复跑一遍并再插一条 backtest_results —— 用户会看到两条重复结果。
        if task.status == "success":
            existing = backtest_repo.get_result_by_task(db, task_id)
            if existing is not None:
                logger.info("backtest task_id=%s already succeeded, skip (idempotent)", task_id)
                return {
                    "task_id": task_id,
                    "result_id": existing.id,
                    "metrics": existing.metrics_json,
                    "idempotent": True,
                }

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

        # G08（P1-4a）：策略在**独立子进程**内执行 —— 死循环/吃内存的策略不会拖垮 worker 主进程；
        # 进度经管道回传，DB 写入仍全部发生在父进程（本函数），保持事务语义不变。
        with backtest_monitor.track_run(task.period) as timing:
            if settings.BACKTEST_SUBPROCESS_ENABLED:
                out = run_isolated(
                    strategy.code,
                    strategy.params,
                    bars_dict,
                    config,
                    grace=settings.BACKTEST_SUBPROCESS_GRACE,
                    cpu_seconds=settings.BACKTEST_CPU_LIMIT_SECONDS,
                    memory_bytes=settings.BACKTEST_MEMORY_LIMIT_MB * 1024 * 1024,
                    on_progress=_progress,
                )
            else:
                from app.backtest.engine import BacktestEngine

                # 仅本地排查用：进程内执行，无隔离/资源上限保护
                out = BacktestEngine(config).run(strategy.code, strategy.params, bars_dict, progress_cb=_progress)
        m = metrics.compute_metrics(
            out["trades"], out["equity_curve"], out["initial_cash"],
            out["start_ts"], out["end_ts"], task.period,
            open_position=out.get("open_position"),
        )
        result = backtest_repo.create_result(
            db, task_id, task.strategy_id, task.symbol_id, m, out["start_ts"], out["end_ts"],
            equity_curve=_serialize_curve(out["equity_curve"]),
            trades=_serialize_trades(out["trades"]),
        )
        backtest_repo.update_task(db, task_id, status="success", progress=100, error=None)
        db.commit()  # 结果 + 任务 success 原子写入

        _save_backtest_memory(db, strategy.user_id, strategy.title, symbol, result.id, m)
        _notify_backtest_done(db, strategy.user_id, task_id, symbol.name, "success", m)
        # G25：监控埋点（耗时分布 + 内存峰值 + 清零连续失败计数），best-effort 不影响主链路
        backtest_monitor.record_success(
            task.strategy_id,
            task_id,
            task.period,
            timing["duration_s"] or 0.0,
            (out.get("_subprocess") or {}).get("peak_rss_bytes"),
        )
        return {"task_id": task_id, "result_id": result.id, "metrics": m}
    except BacktestTimeout as e:
        raise BacktestFatalError(f"回测超时: {e}") from e
    except BacktestError as e:
        raise BacktestFatalError(str(e)) from e
    finally:
        db.close()


def release_quota(task_id: int, quota_token: str | None) -> None:
    """释放 per-user 并发配额（G08）。``quota_token`` 为空（历史/进程内调用）时跳过。

    在任务**终态**调用：成功、业务失败、重试耗尽。**重试中的任务不释放** ——
    它仍占着一个并发位，否则重试期间用户可以超额提交。
    worker 被 SIGKILL 等极端情况下不会走到这里，由 ``BACKTEST_QUOTA_STALE_SECONDS``
    的过期清理兜底自愈。
    """
    if not quota_token:
        return
    db = get_session()
    try:
        task = backtest_repo.get_task(db, task_id)
        if task is None:
            return
        strategy = db.get(TradingStrategy, task.strategy_id)
        if strategy is not None:
            backtest_quota.release(strategy.user_id, quota_token)
    except Exception as e:  # noqa: BLE001 —— 释放失败不应影响任务终态
        logger.warning("release backtest quota failed task_id=%s: %s", task_id, e)
    finally:
        db.close()


def _notify_backtest_done(
    db: Session, user_id: int, task_id: int, symbol_name: str, status: str, metrics: dict | None = None
) -> None:
    """回测完成写站内通知（G16，best-effort，失败不影响回测主链路）。"""
    try:
        from app.services import notification_service

        summary = None
        if status == "success" and metrics:
            win = metrics.get("win_rate")
            ret = metrics.get("total_return")
            if win is not None and ret is not None:
                summary = f"胜率 {win:.1%}，总收益 {ret:+.2%}。点击查看完整结果。"
        notification_service.notify_backtest_complete(db, user_id, task_id, symbol_name, status, summary)
        db.commit()
    except Exception:  # noqa: BLE001
        logger.warning("notify backtest done failed task_id=%s (best-effort)", task_id, exc_info=True)
        db.rollback()


def mark_task_failed(task_id: int, error: str) -> None:
    db = get_session()
    try:
        task = backtest_repo.get_task(db, task_id)
        backtest_repo.update_task(db, task_id, status="failed", error=error[:1000])
        db.commit()
        # G25：失败原因统计 + 连续失败判定（best-effort，Redis 不可用只降级不报错）
        if task is not None:
            backtest_monitor.record_failure(task.strategy_id, task_id, error)
        # G16：回测失败也通知（best-effort）
        if task is not None:
            strategy = db.get(TradingStrategy, task.strategy_id)
            symbol = db.get(Symbol, task.symbol_id)
            if strategy is not None:
                _notify_backtest_done(
                    db, strategy.user_id, task_id, symbol.name if symbol else "标的", "failed"
                )
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


def list_tasks(
    db: Session, user_id: int, strategy_id: int | None = None, page: int = 1, size: int = 20
) -> tuple[list, int]:
    """回测任务列表分页（P1-6a），返回 (rows, total)。"""
    page = max(1, page)
    size = max(1, min(size, 100))
    offset = (page - 1) * size

    if strategy_id is not None:
        if not _strategy_owned(db, user_id, strategy_id):
            raise ApiError(status_code=404, code=40420, msg="策略不存在")
        rows = backtest_repo.list_tasks_by_strategy(db, strategy_id, offset=offset, limit=size)
        return rows, backtest_repo.count_tasks_by_strategy(db, strategy_id)

    # 当前用户全部策略的任务（先按 user 取出策略 id，再按 strategy_id 过滤）
    ids = [s.id for s in strategy_repo.list_strategies(db, user_id)]
    if not ids:
        return [], 0
    rows = backtest_repo.list_tasks_by_strategies(db, ids, offset=offset, limit=size)
    return rows, backtest_repo.count_tasks_by_strategies(db, ids)


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
def _iso(ts) -> str | None:
    """datetime → ISO8601 字符串（JSONB 可序列化；naive 按 UTC 标注，与 DB 口径一致）。"""
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return (ts if ts.tzinfo else ts.replace(tzinfo=UTC)).isoformat()
    return str(ts)


def _serialize_curve(curve: list[dict] | None) -> list[dict] | None:
    """资金曲线序列化（G32）：ts 转 ISO8601，其余字段原样保留。"""
    if not curve:
        return None
    return [
        {
            "ts": _iso(p.get("ts")),
            "equity": float(p.get("equity", 0)),
            "cash": float(p.get("cash", 0)),
            "pos": int(p.get("pos", 0)),
            "price": float(p.get("price", 0)),
        }
        for p in curve
    ]


def _realized_pnl_by_sell(trades: list[dict]) -> list[float]:
    """给每笔卖出分摊「已实现净盈亏」（G32 明细表列，与胜率同一口径）。

    复用 metrics._pair_trades（G20 净盈亏 + FIFO 成本 + 费用按股数分摊），
    避免前端自算导致口径漂移（项目硬约束：前端不得计算复杂指标）。
    一笔卖单可能拆成多段配对，按其 shares 之和恒等于该卖单 shares 推进游标。
    """
    sells = [t for t in trades if t["side"] == "sell"]
    if not sells:
        return []
    pairs = metrics._pair_trades(trades)
    out = [0.0] * len(sells)
    si = 0
    remaining = float(sells[0]["shares"])
    for p in pairs:
        if si >= len(sells):
            break
        out[si] += float(p.get("net_pnl", p["pnl"]))
        remaining -= float(p["shares"])
        if remaining <= 0:
            si += 1
            remaining = float(sells[si]["shares"]) if si < len(sells) else 0.0
    return [round(v, 2) for v in out]


def _serialize_trades(trades: list[dict] | None) -> list[dict] | None:
    """买卖流水序列化（G32）：ts 转 ISO8601；reason 供前端区分止损/止盈样式；
    卖出笔带 realized_pnl（已实现净盈亏，买入笔为 null）。"""
    if not trades:
        return None
    realized = _realized_pnl_by_sell(trades)
    out: list[dict] = []
    si = 0
    for t in trades:
        is_sell = t.get("side") == "sell"
        out.append(
            {
                "ts": _iso(t.get("ts")),
                "side": t.get("side"),
                "price": float(t.get("price", 0)),
                "shares": int(t.get("shares", 0)),
                "amount": float(t.get("amount", 0)),
                "fee": float(t.get("fee", 0)),
                "reason": t.get("reason", "signal"),
                "realized_pnl": realized[si] if is_sell and si < len(realized) else None,
            }
        )
        if is_sell:
            si += 1
    return out


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

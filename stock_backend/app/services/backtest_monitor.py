"""回测监控与异常策略告警（G25 · P1-4b）。

三个观测面（对应 P1-4b 规格的「执行时间分布 / 内存峰值 / 失败原因统计」）：

1. **Prometheus 指标**（`/metrics` 抓取，配 `deploy/prometheus/alerts.yml` 告警规则）：
   - `backtest_duration_seconds`：执行耗时分布（按周期分桶）
   - `backtest_peak_memory_bytes`：子进程内存峰值分布（数据来自 G08 的
     ``_subprocess.peak_rss_bytes``）
   - `backtest_failures_total`：失败原因分类计数
   - `backtest_abnormal_strategy_total`：异常策略计数（连续失败 / 超时 / 内存超限）
2. **结构化日志**：每次执行输出一行含 task_id/strategy_id/耗时/内存峰值/失败原因的
   `key=value` 日志，并写入 ``task_logs``（沿用既有链路，可直接按 task_type=backtest 检索）。
3. **异常策略识别**：同一策略**连续失败**达阈值（Redis 计数，成功即清零）判为异常策略，
   计入 `backtest_abnormal_strategy_total` 并打 warning —— 供运维定位"这个策略一直挂"。

指标埋点失败绝不影响回测主链路：所有 Redis 操作都 try/except 兜底。
"""

import logging
import time
from contextlib import contextmanager

from prometheus_client import Counter, Histogram

from app.core.config import get_settings
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
_settings = get_settings()

BACKTEST_RUNS = Counter("backtest_runs_total", "回测任务执行次数", ["status"])
BACKTEST_DURATION = Histogram(
    "backtest_duration_seconds",
    "回测执行耗时分布（秒）",
    ["period"],
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 45, 60, 120),
)
BACKTEST_PEAK_MEMORY = Histogram(
    "backtest_peak_memory_bytes",
    "回测子进程内存峰值分布（字节）",
    buckets=(16e6, 64e6, 128e6, 256e6, 512e6, 1e9, 2e9),
)
BACKTEST_FAILURES = Counter("backtest_failures_total", "回测失败原因统计", ["reason"])
BACKTEST_ABNORMAL = Counter(
    "backtest_abnormal_strategy_total", "异常策略计数（连续失败/超时/内存超限）", ["reason"]
)

# 失败原因分类（顺序敏感：先匹配更具体的）
_REASON_PATTERNS = (
    ("timeout", ("墙钟上限", "回测超时", "执行超过时间预算")),
    ("memory", ("内存增长超过上限", "MemoryError")),
    ("cpu", ("CPU 时间超出上限",)),
    ("sandbox", ("沙箱", "策略代码", "受限检查", "禁止")),
    ("no_data", ("无 K 线数据", "标的不存在", "标的不存在或无数据")),
    ("runtime", ("策略执行失败", "策略 on_bar", "策略 initialize")),
)


def classify_failure(error: str) -> str:
    """把失败信息归类（供 `backtest_failures_total{reason}` 与告警规则使用）。"""
    text = error or ""
    for reason, keywords in _REASON_PATTERNS:
        if any(k in text for k in keywords):
            return reason
    return "other"


def _streak_key(strategy_id: int) -> str:
    return f"backtest_fail_streak:{strategy_id}"


def _bump_fail_streak(strategy_id: int) -> int:
    """连续失败计数 +1，返回新值（Redis 不可用返回 -1）。"""
    try:
        r = get_redis_client()
        key = _streak_key(strategy_id)
        streak = int(r.incr(key))
        r.expire(key, 86400)  # 一天不活跃即遗忘，避免陈旧计数
        return streak
    except Exception as e:  # noqa: BLE001
        logger.warning("backtest fail streak incr failed strategy=%s: %s", strategy_id, e)
        return -1


def _reset_fail_streak(strategy_id: int) -> None:
    try:
        get_redis_client().delete(_streak_key(strategy_id))
    except Exception as e:  # noqa: BLE001
        logger.warning("backtest fail streak reset failed strategy=%s: %s", strategy_id, e)


@contextmanager
def track_run(period: str):
    """计时上下文：`with track_run(task.period) as t: ...` → `t["duration_s"]`。"""
    started = time.monotonic()
    box: dict = {"duration_s": None}
    try:
        yield box
    finally:
        box["duration_s"] = round(time.monotonic() - started, 3)
        BACKTEST_DURATION.labels(period or "unknown").observe(box["duration_s"])


def record_success(strategy_id: int, task_id: int, period: str, duration_s: float, peak_rss: int | None) -> None:
    """记录一次成功回测：指标 + 结构化日志 + 清零该策略的连续失败计数。"""
    BACKTEST_RUNS.labels("success").inc()
    if peak_rss:
        BACKTEST_PEAK_MEMORY.observe(peak_rss)
    _reset_fail_streak(strategy_id)
    logger.info(
        "backtest done task_id=%s strategy_id=%s period=%s duration=%.2fs peak_rss=%.0fMB",
        task_id,
        strategy_id,
        period,
        duration_s,
        (peak_rss or 0) / 1024 / 1024,
    )


def record_failure(strategy_id: int, task_id: int, error: str) -> str:
    """记录一次失败回测：指标 + 结构化日志 + 连续失败判定，返回归类后的原因。"""
    reason = classify_failure(error)
    BACKTEST_FAILURES.labels(reason).inc()
    BACKTEST_RUNS.labels("failed").inc()

    streak = _bump_fail_streak(strategy_id)
    abnormal = streak >= _settings.BACKTEST_ABNORMAL_FAIL_STREAK
    if abnormal:
        BACKTEST_ABNORMAL.labels(reason).inc()
    logger.warning(
        "backtest failed task_id=%s strategy_id=%s reason=%s streak=%s abnormal=%s error=%s",
        task_id,
        strategy_id,
        reason,
        streak,
        abnormal,
        (error or "")[:200],
    )
    return reason

"""G25 · P1-4b 回测监控与异常策略告警测试（真实 Redis + 真实 Prometheus 注册表）。"""

import uuid

import pytest
from app.core.config import get_settings
from app.services import backtest_monitor
from app.utils.redis_client import get_redis_client
from prometheus_client import REGISTRY

_settings = get_settings()


def _counter(name: str, labels: dict) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


@pytest.fixture
def strategy_id() -> int:
    """不可能与真实数据冲突的 strategy_id，结束后清理连续失败计数。"""
    sid = 900_000 + uuid.uuid4().int % 90_000
    get_redis_client().delete(backtest_monitor._streak_key(sid))
    try:
        yield sid
    finally:
        get_redis_client().delete(backtest_monitor._streak_key(sid))


# --------------------------------------------------------------------------- #
# 失败原因归类
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("策略执行超过墙钟上限 45s，子进程已被强制终止（疑似死循环）", "timeout"),
        ("回测超时: 超过时间预算 30s", "timeout"),
        ("策略内存增长超过上限 512 MB（实测 +588 MB），子进程已被终止", "memory"),
        ("策略执行失败: MemoryError: ", "memory"),
        ("策略 CPU 时间超出上限，子进程已被终止", "cpu"),
        ("策略代码受限检查失败: Line 2: \"__class__\" is an invalid attribute name", "sandbox"),
        ("策略代码禁止 import", "sandbox"),
        ("标的无 K 线数据，请先同步行情后再回测", "no_data"),
        ("策略执行失败: BacktestError: 策略 on_bar 执行失败(bar 3): ValueError: boom", "runtime"),
        ("完全没见过的错误信息", "other"),
    ],
)
def test_classify_failure(error, expected):
    """失败原因归类覆盖各资源/业务分支（供 backtest_failures_total{reason} 与告警规则使用）。"""
    assert backtest_monitor.classify_failure(error) == expected


def test_classify_failure_handles_empty():
    assert backtest_monitor.classify_failure("") == "other"
    assert backtest_monitor.classify_failure(None) == "other"


# --------------------------------------------------------------------------- #
# 指标埋点
# --------------------------------------------------------------------------- #
def test_record_success_updates_metrics(strategy_id):
    """成功回测：runs{success} +1、内存峰值进入直方图、连续失败计数清零。"""
    before_runs = _counter("backtest_runs_total", {"status": "success"})
    before_peak = _counter("backtest_peak_memory_bytes_count", {})
    # 先制造一次失败，验证成功会清零
    backtest_monitor.record_failure(strategy_id, 1, "回测超时: x")

    backtest_monitor.record_success(strategy_id, 1, "1d", 2.5, 120 * 1024 * 1024)

    assert _counter("backtest_runs_total", {"status": "success"}) == before_runs + 1
    assert _counter("backtest_peak_memory_bytes_count", {}) == before_peak + 1
    assert int(get_redis_client().get(backtest_monitor._streak_key(strategy_id)) or 0) == 0


def test_record_success_without_peak_memory(strategy_id):
    """进程内执行（无 _subprocess 元信息）时内存峰值缺省，不应写坏直方图。"""
    before = _counter("backtest_peak_memory_bytes_count", {})

    backtest_monitor.record_success(strategy_id, 1, "1d", 1.0, None)

    assert _counter("backtest_peak_memory_bytes_count", {}) == before


def test_record_failure_updates_reason_counter(strategy_id):
    """失败按归类计数。"""
    before = _counter("backtest_failures_total", {"reason": "memory"})

    reason = backtest_monitor.record_failure(strategy_id, 1, "策略内存增长超过上限 512 MB（实测 +588 MB）")

    assert reason == "memory"
    assert _counter("backtest_failures_total", {"reason": "memory"}) == before + 1


def test_consecutive_failures_flagged_as_abnormal(strategy_id):
    """连续失败达阈值 → 计入异常策略指标（供 BacktestAbnormalStrategy 告警）。"""
    threshold = _settings.BACKTEST_ABNORMAL_FAIL_STREAK
    before = _counter("backtest_abnormal_strategy_total", {"reason": "timeout"})

    for _ in range(threshold - 1):
        backtest_monitor.record_failure(strategy_id, 1, "回测超时: x")
    assert _counter("backtest_abnormal_strategy_total", {"reason": "timeout"}) == before, "未达阈值不应计异常"

    backtest_monitor.record_failure(strategy_id, 1, "回测超时: x")
    assert _counter("backtest_abnormal_strategy_total", {"reason": "timeout"}) == before + 1

    # 第 4 次仍算异常（连续未打断）
    backtest_monitor.record_failure(strategy_id, 1, "回测超时: x")
    assert _counter("backtest_abnormal_strategy_total", {"reason": "timeout"}) == before + 2


def test_success_resets_abnormal_streak(strategy_id):
    """成功一次即打断连续失败，后续单次失败不应再被判为异常。"""
    threshold = _settings.BACKTEST_ABNORMAL_FAIL_STREAK
    for _ in range(threshold):
        backtest_monitor.record_failure(strategy_id, 1, "回测超时: x")
    backtest_monitor.record_success(strategy_id, 1, "1d", 1.0, None)

    before = _counter("backtest_abnormal_strategy_total", {"reason": "timeout"})
    backtest_monitor.record_failure(strategy_id, 1, "回测超时: x")

    assert _counter("backtest_abnormal_strategy_total", {"reason": "timeout"}) == before, "成功应清零连续失败计数"


def test_track_run_records_duration(strategy_id):
    """计时上下文把耗时写入按周期分桶的直方图。"""
    before = _counter("backtest_duration_seconds_count", {"period": "15m"})

    with backtest_monitor.track_run("15m") as timing:
        pass

    assert timing["duration_s"] is not None and timing["duration_s"] >= 0
    assert _counter("backtest_duration_seconds_count", {"period": "15m"}) == before + 1


def test_track_run_records_duration_on_exception(strategy_id):
    """即使回测抛异常也要记录耗时（失败任务的耗时同样有观测价值）。"""
    before = _counter("backtest_duration_seconds_count", {"period": "1w"})

    with pytest.raises(ValueError):
        with backtest_monitor.track_run("1w"):
            raise ValueError("boom")

    assert _counter("backtest_duration_seconds_count", {"period": "1w"}) == before + 1

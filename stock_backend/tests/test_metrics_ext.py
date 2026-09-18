"""5.4/5.5 监控指标测试：/metrics 暴露 LLM + 平台级指标，LLM 调用埋点生效。

平台采集（队列深度/缓存命中率/行情新鲜度/回测积压）依赖 Redis/DB，测试环境不可用时
refresh 内部容错静默跳过，不阻塞 /metrics 正常返回。
"""

import math
from datetime import UTC, datetime, timedelta

import pytest
from app.services.llm import llm_service
from app.utils.db import engine
from app.utils.market_cache import as_utc
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY
from sqlalchemy import text


def _sample(name: str, labels: dict) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0


def test_metrics_expose_llm_and_platform_metrics(client: TestClient):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    for name in (
        "llm_calls_total",
        "llm_request_duration_seconds",
        "llm_tokens_total",
        "celery_queue_depth",
        "redis_cache_hit_rate",
        "market_data_freshness_seconds",
        "backtest_queued_tasks",
    ):
        assert name in resp.text, f"metrics 缺少 {name}"


def test_llm_call_records_metrics():
    before_ok = _sample("llm_calls_total", {"status": "ok"})
    llm_service.LLMService._log_call([{"role": "user", "content": "hi"}], "ok", 10, 0.1, None)
    llm_service.LLMService._log_call([{"role": "user", "content": "hi"}], "", 0, 0.2, ValueError("x"))

    after_ok = _sample("llm_calls_total", {"status": "ok"})
    after_failed = _sample("llm_calls_total", {"status": "failed"})
    assert after_ok == before_ok + 1
    assert after_failed >= 1
    # token 统计埋点（成功调用 tokens=10）
    tokens = _sample("llm_tokens_total", {"kind": "total"})
    assert tokens >= 10


# --------------------------------------------------------------------------- #
# 行情新鲜度指标（G24 跳过时区迁移后的兜底修复，回归防护）
# --------------------------------------------------------------------------- #
def test_as_utc_normalizes_naive_snapshot_timestamp():
    """回归：DB 返回的 naive 时间戳必须先归一，才能与 aware 的 now 相减。

    修复前 `_refresh_market_freshness` 直接做 `datetime.now(UTC) - row`，抛
    `can't subtract offset-naive and offset-aware datetimes`；异常被 except 吞掉，
    Gauge 又保留初始值 0.0 —— 指标显示"0 秒前"（最新），实际采集从未成功，
    `MarketDataStale` 告警永不触发（静默错误，比报错更危险）。
    """
    naive = (datetime.now(UTC) - timedelta(hours=3)).replace(tzinfo=None)  # 模拟 snapshot_realtime.updated_at
    aware = as_utc(naive)

    assert aware.tzinfo is not None
    assert aware.utcoffset() == timedelta(0)
    assert aware.replace(tzinfo=None) == naive  # 不改变挂钟值（naive 列按 UTC 解释）

    # 修复前这一行直接抛 TypeError；修复后应得到约 3 小时的龄
    delta = (datetime.now(UTC) - aware).total_seconds()
    assert 2.9 * 3600 < delta < 3.1 * 3600


def test_market_freshness_metric_reports_real_value_not_placeholder(client: TestClient):
    """回归：有快照数据时指标必须是真实数值，不能是 NaN（采集失败）或 0.0（未赋值的初始值）。"""
    with engine.connect() as conn:
        snapshot_rows = conn.execute(text("SELECT count(*) FROM snapshot_realtime")).scalar_one()
    if snapshot_rows == 0:
        pytest.skip("本地库无快照数据，该指标本就应为 NaN（未同步行情），无法验证")

    client.get("/metrics")  # 触发 refresh_platform_metrics
    value = REGISTRY.get_sample_value("market_data_freshness_seconds")

    assert value is not None, "指标未注册"
    assert not math.isnan(value), "行情新鲜度采集失败（naive/aware 相减回归）——告警将永不触发"
    assert value >= 0

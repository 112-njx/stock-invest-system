"""5.4/5.5 监控指标测试：/metrics 暴露 LLM + 平台级指标，LLM 调用埋点生效。

平台采集（队列深度/缓存命中率/行情新鲜度/回测积压）依赖 Redis/DB，测试环境不可用时
refresh 内部容错静默跳过，不阻塞 /metrics 正常返回。
"""

from app.services.llm import llm_service
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY


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

"""3.2 LLM 封装测试：熔断器状态机、限流令牌桶、LLMService 重试/流式/降级（假 provider）。"""

import types

import pytest
from app.services.llm.circuit_breaker import BreakerState, CircuitBreaker
from app.services.llm.llm_service import (
    LLMAuthError,
    LLMCircuitOpenError,
    LLMContentFilteredError,
    LLMError,
    LLMQuotaError,
    LLMRateLimitError,
    LLMService,
    LLMTimeoutError,
    TokenBucket,
    _classify_provider_error,
    classify_llm_error,
)
from app.services.llm.providers.base import BaseLLMProvider, LLMResult


def _fast_retry(monkeypatch, max_retries=2, backoff=0.01):
    """加速重试测试：替换 llm_service 模块级 settings 为重试参数（避免真实退避等待）。"""
    fake = types.SimpleNamespace(
        LLM_MAX_RETRIES=max_retries,
        LLM_RETRY_BACKOFF=backoff,
        LLM_TIMEOUT=5,
        LLM_CIRCUIT_FAILURE_THRESHOLD=5,
        LLM_CIRCUIT_COOLDOWN=60,
        LLM_RATE_LIMIT_RPM=30,
    )
    monkeypatch.setattr("app.services.llm.llm_service.settings", fake)
    return fake


# ---- 熔断器 ----
def test_breaker_closed_to_open_on_failures():
    b = CircuitBreaker(failure_threshold=3, cooldown=60)
    assert b.state == BreakerState.CLOSED
    for _ in range(3):
        b.on_failure()
    assert b.state == BreakerState.OPEN
    assert not b.allow_request()  # 熔断期拒绝


def test_breaker_half_open_probe_success_resets():
    b = CircuitBreaker(failure_threshold=1, cooldown=0.05)
    b.on_failure()
    assert b.state == BreakerState.OPEN
    b._opened_at = b._opened_at - 60  # 强制冷却结束（测试用）
    assert b.allow_request()  # 半开放行一个探测
    assert b.state == BreakerState.HALF_OPEN
    assert not b.allow_request()  # 探测未返回前，其余拒绝
    b.on_success()
    assert b.state == BreakerState.CLOSED
    assert b.allow_request()


def test_breaker_half_open_probe_failure_reopens():
    b = CircuitBreaker(failure_threshold=2, cooldown=0.05)
    b.on_failure()
    b.on_failure()
    assert b.state == BreakerState.OPEN
    b._opened_at = b._opened_at - 60
    assert b.allow_request()
    b.on_failure()  # 探测失败 → 重新熔断
    assert b.state == BreakerState.OPEN
    assert not b.allow_request()


def test_breaker_reset():
    b = CircuitBreaker(failure_threshold=1, cooldown=60)
    b.on_failure()
    b.reset()
    assert b.state == BreakerState.CLOSED
    assert b.allow_request()


# ---- 限流令牌桶 ----
async def test_token_bucket_limits():
    b = TokenBucket(rate_per_minute=3)
    ok = [await b.acquire() for _ in range(3)]
    assert ok == [True, True, True]
    assert not await b.acquire()  # 已耗尽


# ---- LLMService（假 provider）----
class FakeProvider(BaseLLMProvider):
    name = "fake"

    def __init__(self, fail_times: int = 0, chunks: list[str] | None = None):
        self.fail_times = fail_times  # 前 N 次调用抛错，模拟断流
        self.calls = 0
        self.chunks = chunks or ["你", "好"]

    async def ainvoke(self, messages, temperature=None) -> LLMResult:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("fake network down")
        return LLMResult(text="".join(self.chunks), model="fake", tokens=5)

    async def astream(self, messages, temperature=None):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("fake network down")
        for c in self.chunks:
            yield c


async def test_llm_service_retry_then_success(monkeypatch):
    _fast_retry(monkeypatch)
    svc = LLMService(FakeProvider(fail_times=2, chunks=["成", "功"]))
    result = await svc.ainvoke([{"role": "user", "content": "hi"}])  # 失败2次后重试成功
    assert result.text == "成功"
    assert result.tokens == 5
    assert svc.breaker.state == BreakerState.CLOSED


async def test_llm_service_stream_retry_no_duplicate(monkeypatch):
    _fast_retry(monkeypatch)
    svc = LLMService(FakeProvider(fail_times=1, chunks=["流", "式"]))
    parts = [p async for p in svc.astream([{"role": "user", "content": "hi"}])]
    assert "".join(parts) == "流式"
    assert svc.breaker.state == BreakerState.CLOSED


async def test_llm_service_circuit_opens_after_consecutive_failures(monkeypatch):
    _fast_retry(monkeypatch, max_retries=0)
    svc = LLMService(FakeProvider(fail_times=100))  # 永远失败
    svc.breaker = CircuitBreaker(failure_threshold=1, cooldown=60)
    with pytest.raises(LLMError):
        await svc.ainvoke([{"role": "user", "content": "hi"}])  # 第1次逻辑调用失败 → 熔断
    assert svc.breaker.state == BreakerState.OPEN
    with pytest.raises(LLMError):
        await svc.ainvoke([{"role": "user", "content": "hi"}])  # 熔断快速失败


async def test_llm_service_rate_limit_blocks():
    svc = LLMService(FakeProvider())
    svc.bucket = TokenBucket(rate_per_minute=1)
    await svc.ainvoke([{"role": "user", "content": "1"}])
    with pytest.raises(LLMRateLimitError):
        await svc.ainvoke([{"role": "user", "content": "2"}])


def test_llm_available_without_api_key():
    from app.core.config import get_settings

    s = get_settings()
    svc = LLMService(FakeProvider())
    if not s.DEEPSEEK_API_KEY:
        assert not svc.available  # 未配置 key → 降级文案由聊天服务使用


# ---- 5.3 错误分类与错误帧 ----
def test_classify_error_by_exception_type():
    assert classify_llm_error(LLMRateLimitError("频繁"))["code"] == "RATE_LIMITED"
    assert classify_llm_error(LLMAuthError("key 无效"))["code"] == "TOKEN_INVALID"
    assert classify_llm_error(LLMQuotaError("余额不足"))["code"] == "TOKEN_QUOTA"
    assert classify_llm_error(LLMCircuitOpenError("熔断"))["code"] == "PROVIDER_UNAVAILABLE"
    assert classify_llm_error(LLMContentFilteredError("违规"))["code"] == "CONTENT_FILTERED"
    assert classify_llm_error(LLMTimeoutError("超时"))["code"] == "TIMEOUT"
    assert classify_llm_error(LLMError("网络"))["code"] == "NETWORK_ERROR"


def test_classify_error_retryable_flags():
    assert classify_llm_error(LLMRateLimitError("x"))["retryable"] is True
    assert classify_llm_error(LLMRateLimitError("x"))["retry_after"] == 30
    assert classify_llm_error(LLMAuthError("x"))["retryable"] is False
    assert classify_llm_error(LLMQuotaError("x"))["retryable"] is False
    assert classify_llm_error(LLMContentFilteredError("x"))["retryable"] is False
    assert classify_llm_error(LLMError("x"))["retryable"] is True


def test_classify_provider_error_by_status_code():
    class _StatusError(Exception):
        def __init__(self, status_code):
            self.status_code = status_code

    assert isinstance(_classify_provider_error(_StatusError(401)), LLMAuthError)
    assert isinstance(_classify_provider_error(_StatusError(402)), LLMQuotaError)
    assert isinstance(_classify_provider_error(_StatusError(429)), LLMRateLimitError)


def test_classify_provider_error_by_message():
    assert isinstance(_classify_provider_error(ConnectionError("insufficient balance")), LLMQuotaError)
    assert isinstance(_classify_provider_error(ConnectionError("invalid api key")), LLMAuthError)
    assert isinstance(_classify_provider_error(ConnectionError("rate limit reached")), LLMRateLimitError)
    assert isinstance(_classify_provider_error(ConnectionError("unknown network")), LLMError)


async def test_ainvoke_auth_error_not_retried(monkeypatch):
    """鉴权错误不可重试：provider 抛 401 → 直接 LLMAuthError（不空转重试）。"""

    class _AuthProvider(FakeProvider):
        async def ainvoke(self, messages, temperature=None):
            raise ConnectionError("invalid api key")

    _fast_retry(monkeypatch, max_retries=3, backoff=0.01)
    svc = LLMService(_AuthProvider())
    with pytest.raises(LLMAuthError):
        await svc.ainvoke([{"role": "user", "content": "hi"}])

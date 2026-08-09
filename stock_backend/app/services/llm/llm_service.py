"""LLMService：统一 DeepSeek 调用入口，内置外部调用防护。

防护（借鉴 TradingAgents-CN llm_adapters）：
- 超时：provider 层 timeout；调用方再包 asyncio 超时兜底
- 指数退避重试：失败重试，流式已出首字后不重试（避免重复输出）
- 熔断：连续失败熔断 + 冷却后半开探测
- 限流：进程内令牌桶（RPM）
- token 统计 + 审计日志（结构化 JSON，含 prompt/响应截断/耗时/错误）
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator

from app.core.config import get_settings

from .circuit_breaker import CircuitBreaker
from .providers.base import BaseLLMProvider, LLMResult
from .providers.deepseek import DeepSeekProvider

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMError(RuntimeError):
    """LLM 调用失败（熔断/限流/网络/上游错误统一包装）。"""


class LLMCircuitOpenError(LLMError):
    pass


class LLMRateLimitError(LLMError):
    pass


class TokenBucket:
    """进程内令牌桶限流（RPM）。"""

    def __init__(self, rate_per_minute: int):
        self.capacity = max(1, rate_per_minute)
        self.tokens = float(self.capacity)
        self.refill_per_sec = self.capacity / 60.0
        self.last_refill = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
            self.last_refill = now
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False


class LLMService:
    def __init__(self, provider: BaseLLMProvider | None = None):
        self.provider: BaseLLMProvider = provider or DeepSeekProvider()
        self.breaker = CircuitBreaker(
            failure_threshold=settings.LLM_CIRCUIT_FAILURE_THRESHOLD,
            cooldown=settings.LLM_CIRCUIT_COOLDOWN,
        )
        self.bucket = TokenBucket(settings.LLM_RATE_LIMIT_RPM)

    @property
    def available(self) -> bool:
        """DeepSeek API Key 未配置视为不可用（聊天给出降级文案）。"""
        return bool(settings.DEEPSEEK_API_KEY)

    async def preflight(self) -> None:
        """调用前防护检查（熔断 + 限流）；供 Agent 编排（LangGraph/ReAct）调用前使用。"""
        if not self.breaker.allow_request():
            raise LLMCircuitOpenError("AI 服务熔断保护中，请稍后再试")
        if not await self.bucket.acquire():
            raise LLMRateLimitError("请求过于频繁，请稍后再试")

    # ---- 非流式 ----
    async def ainvoke(self, messages: list[dict], temperature: float | None = None) -> LLMResult:
        if not self.breaker.allow_request():
            raise LLMCircuitOpenError("AI 服务熔断保护中，请稍后再试")
        if not await self.bucket.acquire():
            raise LLMRateLimitError("请求过于频繁，请稍后再试")

        start = time.monotonic()
        last_exc: Exception | None = None
        for attempt in range(settings.LLM_MAX_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    self.provider.ainvoke(messages, temperature=temperature),
                    timeout=settings.LLM_TIMEOUT,
                )
                self.breaker.on_success()
                self._log_call(messages, result.text, result.tokens, time.monotonic() - start, None)
                return result
            except Exception as e:  # noqa: BLE001
                last_exc = e
                if attempt < settings.LLM_MAX_RETRIES:
                    await asyncio.sleep(settings.LLM_RETRY_BACKOFF * (2**attempt))
        self.breaker.on_failure()
        self._log_call(messages, "", 0, time.monotonic() - start, last_exc)
        raise LLMError(f"AI 服务调用失败: {type(last_exc).__name__}: {last_exc}") from last_exc

    # ---- 流式（SSE 透传）----
    async def astream(self, messages: list[dict], temperature: float | None = None) -> AsyncIterator[str]:
        if not self.breaker.allow_request():
            raise LLMCircuitOpenError("AI 服务熔断保护中，请稍后再试")
        if not await self.bucket.acquire():
            raise LLMRateLimitError("请求过于频繁，请稍后再试")

        start = time.monotonic()
        parts: list[str] = []
        yielded_any = False
        last_exc: Exception | None = None
        for attempt in range(settings.LLM_MAX_RETRIES + 1):
            try:
                # 流式超时由 provider 层 ChatOpenAI timeout 保证（流中不套 asyncio.timeout，避免悬挂误判）
                async for piece in self.provider.astream(messages, temperature=temperature):
                    yielded_any = True
                    parts.append(piece)
                    yield piece
                self.breaker.on_success()
                self._log_call(messages, "".join(parts), 0, time.monotonic() - start, None)
                return
            except Exception as e:  # noqa: BLE001
                last_exc = e
                # 已出首字后失败不重试（避免重复输出）；连接前失败则退避重试
                if yielded_any or attempt >= settings.LLM_MAX_RETRIES:
                    break
                await asyncio.sleep(settings.LLM_RETRY_BACKOFF * (2**attempt))
        self.breaker.on_failure()
        self._log_call(messages, "".join(parts), 0, time.monotonic() - start, last_exc)
        raise LLMError(f"AI 服务调用失败: {type(last_exc).__name__}: {last_exc}") from last_exc

    @staticmethod
    def _log_call(messages, text: str, tokens: int, duration: float, error: Exception | None) -> None:
        """LLM 审计日志：prompt 截断 / 响应截断 / token / 耗时 / 错误（结构化 JSON）。"""
        prompt = " | ".join(f"{m.get('role')}: {str(m.get('content'))[:200]}" for m in messages[-3:])
        if error:
            logger.error(
                "llm_call failed",
                extra={"llm_prompt": prompt[:500], "llm_response": text[:200], "llm_tokens": tokens,
                       "llm_duration_ms": round(duration * 1000), "llm_error": str(error)},
            )
        else:
            logger.info(
                "llm_call ok",
                extra={"llm_prompt": prompt[:500], "llm_response": text[:200], "llm_tokens": tokens,
                       "llm_duration_ms": round(duration * 1000)},
            )


_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """单例（进程内共享熔断/限流状态）。"""
    global _service
    if _service is None:
        _service = LLMService()
    return _service

"""LLMService：统一 DeepSeek 调用入口，内置外部调用防护。

防护（借鉴 TradingAgents-CN llm_adapters）：
- 超时：provider 层 timeout；调用方再包 asyncio 超时兜底
- 指数退避重试：失败重试，流式已出首字后不重试（避免重复输出）
- 熔断：连续失败熔断 + 冷却后半开探测
- 限流：进程内令牌桶（RPM）
- token 统计 + 审计日志（结构化 JSON，含 prompt/响应截断/耗时/错误）
"""

# 惰性求值注解（G08 修复）：LLMService.with_api_key 的返回注解引用类自身，
# Python 3.12（容器）在类体执行时急切求值会抛 NameError: name 'LLMService' is not defined，
# 导致 api/worker/beat **整个无法导入启动**；Python 3.13+ 默认惰性故本地不报错。
# 与 store.py 同类问题（见 docs/Agent_main_v0.1/deploy_fixed.md 问题二）。
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable

from app.agent.sse import ErrorCode, build_error_event
from app.agent.token_budget import estimate_tokens
from app.core.config import get_settings
from app.core.metrics import LLM_CALLS, LLM_DURATION, LLM_TOKENS

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


class LLMAuthError(LLMError):
    """用户 token 无效（DeepSeek 401）。"""


class LLMQuotaError(LLMError):
    """用户余额不足（DeepSeek 402）。"""


class LLMContentFilteredError(LLMError):
    """内容违规被过滤（不可重试）。"""


class LLMTimeoutError(LLMError):
    """调用超时。"""


def _inspect_status(exc: Exception) -> int | None:
    """沿异常链（__cause__/__context__）找 HTTP 状态码。"""
    seen: set[int] = set()
    e: BaseException | None = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        for attr in ("status_code", "http_status"):
            v = getattr(e, attr, None)
            if isinstance(v, int):
                return v
        e = e.__cause__ or e.__context__
    return None


def _inspect_text(exc: Exception) -> str:
    """沿异常链拼接错误文本（小写）。"""
    seen: set[int] = set()
    parts: list[str] = []
    e: BaseException | None = exc
    while e is not None and id(e) not in seen:
        seen.add(id(e))
        parts.append(str(e))
        e = e.__cause__ or e.__context__
    return " ".join(parts).lower()


def _classify_provider_error(exc: Exception) -> LLMError:
    """把 provider 抛出的原始异常归类为具体 LLM 异常类型（决定重试策略 + SSE 错误码）。"""
    if isinstance(exc, LLMError):
        return exc
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return LLMTimeoutError("AI 响应超时")
    status = _inspect_status(exc)
    text = _inspect_text(exc)
    if status == 401 or "invalid api key" in text or "authentication" in text or "invalid token" in text or "unauthorized" in text:
        return LLMAuthError("您的DeepSeek API Key无效，请检查配置")
    if status == 402 or "insufficient balance" in text or "balance" in text or "quota" in text or "not enough" in text:
        return LLMQuotaError("您的DeepSeek API 余额不足，请充值后重试")
    if status == 429 or "rate limit" in text or "too many requests" in text:
        return LLMRateLimitError("请求过于频繁，请30秒后重试")
    if "content" in text and ("filter" in text or "policy" in text or "flagged" in text or "moderation" in text):
        return LLMContentFilteredError("内容违规，已被过滤")
    return LLMError(f"AI 服务调用失败: {type(exc).__name__}: {exc}")


def _is_retryable(exc: Exception) -> bool:
    """鉴权/余额/内容过滤错误不可重试，其余可退避重试。"""
    return not isinstance(exc, (LLMAuthError, LLMQuotaError, LLMContentFilteredError))


def classify_llm_error(exc: Exception) -> dict:
    """把异常映射为标准化 SSE 错误帧（阶段五 5.3）。"""
    typed = _classify_provider_error(exc)
    if isinstance(typed, LLMRateLimitError):
        return build_error_event(ErrorCode.RATE_LIMITED, str(typed) or "请求过于频繁，请稍后重试", retry_after=30)
    if isinstance(typed, LLMAuthError):
        return build_error_event(ErrorCode.TOKEN_INVALID, str(typed) or "您的DeepSeek API Key无效，请检查配置")
    if isinstance(typed, LLMQuotaError):
        return build_error_event(ErrorCode.TOKEN_QUOTA, str(typed) or "您的DeepSeek API 余额不足，请充值后重试")
    if isinstance(typed, LLMContentFilteredError):
        return build_error_event(ErrorCode.CONTENT_FILTERED, str(typed) or "内容违规，已被过滤")
    if isinstance(typed, LLMCircuitOpenError):
        return build_error_event(ErrorCode.PROVIDER_UNAVAILABLE, str(typed) or "AI 服务暂时不可用，请稍后重试")
    if isinstance(typed, LLMTimeoutError):
        return build_error_event(ErrorCode.TIMEOUT, str(typed) or "AI 响应超时，请稍后重试")
    return build_error_event(ErrorCode.NETWORK_ERROR, str(typed) or "AI 服务网络异常，请稍后重试")


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
    def __init__(
        self,
        provider: BaseLLMProvider | None = None,
        *,
        api_key: str | None = None,
        breaker: CircuitBreaker | None = None,
        bucket: TokenBucket | None = None,
        usage_sink: Callable[[int, int, bool], None] | None = None,
    ):
        """G14：api_key 为用户自填 key（None = 用服务端默认）；breaker/bucket 可外部注入以共享
        进程级熔断与限流状态；usage_sink 在每次调用结束后回调 (prompt, completion, estimated)。
        """
        self.provider: BaseLLMProvider = provider or DeepSeekProvider(api_key=api_key)
        self.api_key = api_key  # 仅用于判断可用性，不落库不日志
        self.breaker = breaker or CircuitBreaker(
            failure_threshold=settings.LLM_CIRCUIT_FAILURE_THRESHOLD,
            cooldown=settings.LLM_CIRCUIT_COOLDOWN,
        )
        self.bucket = bucket or TokenBucket(settings.LLM_RATE_LIMIT_RPM)
        self.usage_sink = usage_sink

    def with_api_key(
        self, api_key: str | None, usage_sink: Callable[[int, int, bool], None] | None = None
    ) -> LLMService:
        """派生一个绑定用户 key 的实例，**共享**熔断器与限流桶（保护仍是进程级）。"""
        if not api_key:
            return self
        return LLMService(api_key=api_key, breaker=self.breaker, bucket=self.bucket, usage_sink=usage_sink)

    @property
    def available(self) -> bool:
        """用户自填 key 或服务端 key 任一存在即可用；都没有则聊天给出降级文案。"""
        return bool(self.api_key or settings.DEEPSEEK_API_KEY)

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
        last_exc: LLMError | None = None
        for attempt in range(settings.LLM_MAX_RETRIES + 1):
            try:
                result = await asyncio.wait_for(
                    self.provider.ainvoke(messages, temperature=temperature),
                    timeout=settings.LLM_TIMEOUT,
                )
                self.breaker.on_success()
                prompt_t, completion_t, estimated = self._usage_of(result, messages, result.text)
                self._report_usage(prompt_t, completion_t, estimated)
                self._log_call(messages, result.text, result.tokens, time.monotonic() - start, None)
                return result
            except Exception as e:  # noqa: BLE001
                last_exc = _classify_provider_error(e)
                if not _is_retryable(last_exc) or attempt >= settings.LLM_MAX_RETRIES:
                    break
                await asyncio.sleep(settings.LLM_RETRY_BACKOFF * (2**attempt))
        self.breaker.on_failure()
        self._log_call(messages, "", 0, time.monotonic() - start, last_exc)
        raise last_exc

    # ---- 流式（SSE 透传）----
    async def astream(self, messages: list[dict], temperature: float | None = None) -> AsyncIterator[str]:
        if not self.breaker.allow_request():
            raise LLMCircuitOpenError("AI 服务熔断保护中，请稍后再试")
        if not await self.bucket.acquire():
            raise LLMRateLimitError("请求过于频繁，请稍后再试")

        start = time.monotonic()
        parts: list[str] = []
        yielded_any = False
        last_exc: LLMError | None = None
        for attempt in range(settings.LLM_MAX_RETRIES + 1):
            try:
                # 流式超时由 provider 层 ChatOpenAI timeout 保证（流中不套 asyncio.timeout，避免悬挂误判）
                async for piece in self.provider.astream(messages, temperature=temperature):
                    yielded_any = True
                    parts.append(piece)
                    yield piece
                self.breaker.on_success()
                prompt_t, completion_t, estimated = self._stream_usage(messages, "".join(parts))
                self._report_usage(prompt_t, completion_t, estimated)
                self._log_call(messages, "".join(parts), prompt_t + completion_t, time.monotonic() - start, None)
                return
            except Exception as e:  # noqa: BLE001
                last_exc = _classify_provider_error(e)
                # 已出首字后失败不重试（避免重复输出）；连接前失败则退避重试（鉴权/余额/内容过滤不可重试）
                if yielded_any or not _is_retryable(last_exc) or attempt >= settings.LLM_MAX_RETRIES:
                    break
                await asyncio.sleep(settings.LLM_RETRY_BACKOFF * (2**attempt))
        self.breaker.on_failure()
        self._log_call(messages, "".join(parts), 0, time.monotonic() - start, last_exc)
        raise last_exc

    # ---- G14：token 用量统计 ----
    @staticmethod
    def _usage_of(result: LLMResult, messages: list[dict], text: str) -> tuple[int, int, bool]:
        """取本次调用的 (prompt, completion, 是否估算)。上游无 usage 时本地估算（非精确计费）。"""
        if result.prompt_tokens or result.completion_tokens:
            return result.prompt_tokens, result.completion_tokens, False
        return _estimate_pair(messages, text)

    def _stream_usage(self, messages: list[dict], text: str) -> tuple[int, int, bool]:
        """流式调用的 token：优先 provider 在末个 chunk 捕获的 usage，否则本地估算。"""
        usage = getattr(self.provider, "last_usage", (0, 0))
        if usage and (usage[0] or usage[1]):
            return int(usage[0]), int(usage[1]), False
        return _estimate_pair(messages, text)

    def _report_usage(self, prompt_tokens: int, completion_tokens: int, estimated: bool) -> None:
        """回调用量（G14 累计统计）；回调失败不影响主链路。"""
        if self.usage_sink is None:
            return
        try:
            self.usage_sink(prompt_tokens, completion_tokens, estimated)
        except Exception as e:  # noqa: BLE001
            logger.warning("llm usage sink failed: %s", e)

    @staticmethod
    def _log_call(messages, text: str, tokens: int, duration: float, error: Exception | None) -> None:
        """LLM 审计日志 + Prometheus 埋点：prompt/响应截断、token、耗时、错误。"""
        status = "failed" if error else "ok"
        LLM_CALLS.labels(status).inc()
        LLM_DURATION.labels(status).observe(duration)
        LLM_TOKENS.labels("total").inc(tokens)
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


def _estimate_pair(messages: list[dict], text: str) -> tuple[int, int, bool]:
    """本地估算 (prompt, completion) token（字符启发式，供上游无 usage 时兜底）。"""
    prompt = sum(estimate_tokens(str(m.get("content", ""))) + 4 for m in messages)
    return prompt, estimate_tokens(text), True


_service: LLMService | None = None


def get_llm_service() -> LLMService:
    """单例（进程内共享熔断/限流状态）。"""
    global _service
    if _service is None:
        _service = LLMService()
    return _service

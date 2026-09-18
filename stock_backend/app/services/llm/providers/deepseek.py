"""DeepSeek Provider：基于 langchain-openai ChatOpenAI（DeepSeek 兼容 OpenAI 协议）。

注意：langchain-openai 1.x 已无 ChatDeepSeek 类，用 ChatOpenAI + base_url 直连 DeepSeek。
ChatOpenAI 惰性构造：未配置 DEEPSEEK_API_KEY 时（available=False，走降级文案）不抛错。

G14（P0-2）：支持用户自填 API Key —— 构造时可传入 `api_key` 覆盖服务端默认 key；
流式调用开启 `stream_usage=True` 以便取到 usage 字段（累计 token 用量统计用）。
"""

import logging
from collections.abc import AsyncIterator

from langchain_openai import ChatOpenAI

from app.core.config import get_settings

from .base import BaseLLMProvider, LLMResult

logger = logging.getLogger(__name__)
settings = get_settings()


class DeepSeekProvider(BaseLLMProvider):
    name = "deepseek"

    def __init__(self, api_key: str | None = None):
        self.model = settings.DEEPSEEK_MODEL
        # G14：用户自填 key 优先，未填则用服务端默认 key
        self.api_key = api_key or settings.DEEPSEEK_API_KEY
        self._llm: ChatOpenAI | None = None

    def _build(self, temperature: float) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            base_url=settings.DEEPSEEK_BASE_URL,
            temperature=temperature,
            timeout=settings.LLM_TIMEOUT,
            max_retries=0,  # 重试由 LLMService 统一指数退避
            stream_usage=True,  # G14：流式也返回 usage（末个 chunk 带 usage_metadata）
        )

    def _ensure_llm(self) -> ChatOpenAI:
        if self._llm is None:
            self._llm = self._build(settings.LLM_TEMPERATURE)
        return self._llm

    @property
    def raw_model(self) -> ChatOpenAI:
        """供 create_agent 绑定工具用的原始模型实例（惰性构造，无 Key 时抛错由上层捕获）。"""
        return self._ensure_llm()

    def _with_temperature(self, temperature: float | None) -> ChatOpenAI:
        if temperature is None:
            return self._ensure_llm()
        # 每次调用用独立实例，避免共享温度状态
        return self._build(temperature)

    async def ainvoke(self, messages: list[dict], temperature: float | None = None) -> LLMResult:
        llm = self._with_temperature(temperature)
        resp = await llm.ainvoke(messages)
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        prompt_t, completion_t = self._usage_breakdown(resp)
        return LLMResult(
            text=text,
            model=self.model,
            tokens=prompt_t + completion_t,
            prompt_tokens=prompt_t,
            completion_tokens=completion_t,
        )

    async def astream(
        self, messages: list[dict], temperature: float | None = None
    ) -> AsyncIterator[str]:
        """流式产出文本增量；usage 由 `last_usage` 暴露给调用方（末个 chunk 携带）。"""
        llm = self._with_temperature(temperature)
        self.last_usage = (0, 0)
        async for chunk in llm.astream(messages):
            usage = getattr(chunk, "usage_metadata", None)
            if usage:
                self.last_usage = (
                    int(usage.get("input_tokens") or 0),
                    int(usage.get("output_tokens") or 0),
                )
            piece = chunk.content if hasattr(chunk, "content") else str(chunk)
            if piece:
                yield piece

    # 最近一次流式调用的 (prompt_tokens, completion_tokens)
    last_usage: tuple[int, int] = (0, 0)

    @staticmethod
    def _usage_breakdown(resp) -> tuple[int, int]:
        """从响应元数据取 (prompt, completion) token；不可得返回 (0, 0) 由服务层估算。"""
        usage = getattr(resp, "usage_metadata", None)
        if usage:
            prompt = int(usage.get("input_tokens") or 0)
            completion = int(usage.get("output_tokens") or 0)
            if prompt or completion:
                return prompt, completion
            total = int(usage.get("total_tokens") or 0)
            if total:
                return total, 0
        return 0, 0

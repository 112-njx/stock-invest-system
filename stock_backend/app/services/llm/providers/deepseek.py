"""DeepSeek Provider：基于 langchain-openai ChatOpenAI（DeepSeek 兼容 OpenAI 协议）。

注意：langchain-openai 1.x 已无 ChatDeepSeek 类，用 ChatOpenAI + base_url 直连 DeepSeek。
ChatOpenAI 惰性构造：未配置 DEEPSEEK_API_KEY 时（available=False，走降级文案）不抛错。
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

    def __init__(self):
        self.model = settings.DEEPSEEK_MODEL
        self._llm: ChatOpenAI | None = None

    def _build(self, temperature: float) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.model,
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            temperature=temperature,
            timeout=settings.LLM_TIMEOUT,
            max_retries=0,  # 重试由 LLMService 统一指数退避
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
        tokens = self._usage_tokens(resp)
        return LLMResult(text=text, model=self.model, tokens=tokens)

    async def astream(self, messages: list[dict], temperature: float | None = None) -> AsyncIterator[str]:
        llm = self._with_temperature(temperature)
        async for chunk in llm.astream(messages):
            piece = chunk.content if hasattr(chunk, "content") else str(chunk)
            if piece:
                yield piece

    @staticmethod
    def _usage_tokens(resp) -> int:
        """从响应元数据取 token；不可得返回 0（服务层可估算）。"""
        usage = getattr(resp, "usage_metadata", None)
        if usage:
            total = usage.get("total_tokens")
            if total:
                return int(total)
        return 0

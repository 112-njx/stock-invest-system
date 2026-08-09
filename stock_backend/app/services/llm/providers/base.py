"""LLM Provider 抽象：统一流式/非流式接口，未来可插拔多供应商。

借鉴 TradingAgents-CN llm_adapters 多适配器架构：第一版仅 DeepSeek，
新增模型只需实现本抽象并注册到 factories。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass
class LLMResult:
    """一次 LLM 调用的结构化结果。"""

    text: str
    model: str
    tokens: int = 0  # 总 token（prompt+completion），不可得时估算


class BaseLLMProvider(ABC):
    model: str

    @abstractmethod
    async def ainvoke(self, messages: list[dict], temperature: float | None = None) -> LLMResult:
        """非流式调用，返回完整文本 + token 统计。"""

    @abstractmethod
    async def astream(self, messages: list[dict], temperature: float | None = None) -> AsyncIterator[str]:
        """流式调用，逐字/逐块产出文本增量。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """provider 标识（deepseek/qwen/...）。"""

    @property
    def raw_model(self):
        """底层可绑定工具的 ChatModel（供 Agent 编排使用）；无则返回 None。"""
        return None

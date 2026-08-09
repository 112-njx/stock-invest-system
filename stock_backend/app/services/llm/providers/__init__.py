"""LLM Provider 注册。"""

from .base import BaseLLMProvider, LLMResult
from .deepseek import DeepSeekProvider

__all__ = ["BaseLLMProvider", "LLMResult", "DeepSeekProvider"]

"""Token 预算控制（阶段八 8.2）：发送 LLM 前估算 token 总量，超预算时减少完整轮数。

无外部 tokenizer（不引入 tiktoken 依赖），用字符启发式保守估算：
- CJK 字符 ≈ 1 token/字；
- 其他字符 ≈ 4 字符/token（英文字词近似），估算偏保守以提前规避 LLM token limit。
"""

import re

from app.core.config import get_settings

_CJK_RE = re.compile(r"[一-鿿　-〿＀-￯]")

# 完整历史窗口（每轮 = user + assistant 两条）：10轮/8轮/6轮
FULL_ROUND_WINDOWS = [20, 16, 12]

settings = get_settings()


def estimate_tokens(text: str) -> int:
    """估算单段文本 token 数（保守：CJK 1 字/token，其余 4 字符/token）。"""
    if not text:
        return 0
    cjk = len(_CJK_RE.findall(text))
    other = max(0, len(text) - cjk)
    return cjk + (other + 3) // 4


def estimate_messages_tokens(messages: list[dict]) -> int:
    """估算消息列表总 token（含每条消息 ~4 token 协议开销）。"""
    total = 0
    for m in messages:
        total += estimate_tokens(str(m.get("content", ""))) + 4
    return total


def fit_window_to_budget(
    *,
    system_prompt: str,
    all_history: list[dict],
    summary: str | None,
    user_content: str,
    memory_context: str | None,
    tools_tokens: int,
) -> int:
    """按预算返回应保留的完整历史条数（20/16/12），超预算逐级降。

    固定开销 = system prompt + 工具描述 + 当前问题 + 记忆上下文 + 会话摘要；
    完整历史逐级减少直到 ``fixed + history <= max_tokens * ratio``。
    """
    budget = int(settings.LLM_MAX_TOKENS * settings.TOKEN_BUDGET_RATIO)
    fixed = (
        estimate_tokens(system_prompt)
        + tools_tokens
        + estimate_tokens(user_content)
        + (estimate_tokens(memory_context) + 4 if memory_context else 0)
        + (estimate_tokens(f"之前对话摘要：{summary}") + 4 if summary else 0)
    )
    for window in FULL_ROUND_WINDOWS:
        if fixed + estimate_messages_tokens(all_history[-window:]) <= budget:
            return window
    return FULL_ROUND_WINDOWS[-1]

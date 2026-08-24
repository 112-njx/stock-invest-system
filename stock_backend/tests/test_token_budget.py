"""阶段八 8.2 token 预算控制测试。"""

from app.agent.token_budget import estimate_messages_tokens, estimate_tokens, fit_window_to_budget


def test_estimate_tokens_cjk_and_ascii():
    assert estimate_tokens("分析贵州茅台") == 6  # 纯中文 1 字 1 token
    assert estimate_tokens("hello") == 2  # 5 个 ASCII 字符 → (5+3)//4=2
    assert estimate_tokens("") == 0
    assert estimate_tokens("中a") == 2  # 1 CJK + 1 ascii → 1 + (1+3)//4 = 2


def test_estimate_messages_tokens_adds_overhead():
    msgs = [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "ok"}]
    # 你好=2、ok=1，每条消息 +4 协议开销 → 2+1+8=11
    assert estimate_messages_tokens(msgs) == 11


def test_fit_window_to_budget_reduces_when_huge():
    # 每条消息 30000 CJK 字符（≈30000 token），远超预算 → 逐级降到最小窗口 12
    all_history = [{"role": "user", "content": "长" * 30000}] * 30
    window = fit_window_to_budget(
        system_prompt="sys",
        all_history=all_history,
        summary=None,
        user_content="q",
        memory_context=None,
        tools_tokens=0,
    )
    assert window == 12


def test_fit_window_to_budget_keeps_full_when_small():
    all_history = [{"role": "user", "content": "短"}] * 5
    window = fit_window_to_budget(
        system_prompt="sys",
        all_history=all_history,
        summary=None,
        user_content="q",
        memory_context=None,
        tools_tokens=0,
    )
    assert window == 20


def test_fit_window_to_budget_intermediate_window():
    """中等超长历史 → 降到 16 而非 12（逐级降）。"""
    # 每条 3000 token，20 条 ≈ 60082 > 预算，16 条 ≈ 48066 ≤ 预算
    all_history = [{"role": "user", "content": "x" * 12000}] * 30  # 12000 ascii ≈ 3000 token
    window = fit_window_to_budget(
        system_prompt="s",
        all_history=all_history,
        summary=None,
        user_content="q",
        memory_context=None,
        tools_tokens=0,
    )
    assert window == 16

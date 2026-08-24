"""策略生成（3.5 + 阶段八 8.3/8.4）：LangChain with_structured_output 生成策略代码 + JSON 参数。

阶段八升级：
- 三级校验（8.3）：ast.parse 语法 → 接口（initialize/on_bar/签名/禁 import）→ 沙箱 dry-run；
- 生成失败自动重试（8.4）：校验失败把错误信息拼回 prompt 要求修复重生成，最多重试 2 次，
  仍失败抛带模板库入口提示的错误。

借鉴 AgentQuant「自然语言→策略代码」+ QuantDinger「模板化策略」思路：约束回测接口 initialize/on_bar。
"""

import logging
from typing import Any

from app.agent.strategy_validator import validate_strategy
from app.core.config import get_settings
from app.schemas.strategy import StrategyOutput
from app.services.llm import LLMError, LLMService

logger = logging.getLogger(__name__)
settings = get_settings()

_GENERATE_PROMPT = """你是量化策略工程师。根据用户的交易想法，生成一份「可直接回测」的 Python 交易策略。

## 回测策略代码接口（必须严格遵循）
```python
def initialize(context):
    \"\"\"初始化：可读取 context.params（JSON 参数）或做一次性准备。\"\"\"
    ...

def on_bar(bar, context):
    \"\"\"每根 K 线回调。bar 含 ts/open/high/low/close/volume/amount；
    context 提供 pos(当前持仓数)、cash(可用资金)、params(策略参数)，
    并通过 context.buy()/context.sell() 触发交易。\"\"\"
    ...
```

## 要求
1. 代码必须是合法 Python，只用基础语法与简单数值计算（回测沙箱内运行，禁网络/文件操作、禁 import）。
2. 给出完整可运行的 initialize 与 on_bar，逻辑自洽。
3. params 用 JSON 结构给出：entry（入场）/ stop_loss（止损）/ take_profit（止盈）/ position（仓位）四组参数，
   值为简洁的 key-value（如 {{"fast": 5, "slow": 20}}）。
4. strategy_name 简洁命名；description 用中文说明策略逻辑；risk_warning 提示主要风险。
5. 只依据用户描述设计，数据不足时在 description 说明假设。

用户交易想法：
{description}
"""

_RETRY_EXHAUSTED_MSG = "策略生成遇到问题，请尝试调整描述或基于模板创建。"


def _format_errors(errors: list[dict]) -> str:
    """把校验错误列表拼成可读文本（行号 + 错误类型 + 消息）。"""
    lines = []
    for e in errors:
        line = f"第{e['line']}行" if e.get("line") else "未知位置"
        lines.append(f"{line}: {e['message']}")
    return "\n".join(lines)


async def generate_strategy(
    description: str,
    llm_svc: LLMService | None = None,
    structured_model: Any | None = None,
) -> StrategyOutput:
    """生成策略（三级校验 + 失败自动重试最多 2 次）。structured_model 供测试注入。"""
    llm_svc = llm_svc or __import__("app.services.llm", fromlist=["get_llm_service"]).get_llm_service()
    if not llm_svc.available:
        raise LLMError("AI 服务不可用（未配置 DeepSeek API Key），无法生成策略")

    await llm_svc.preflight()
    prompt = _GENERATE_PROMPT.format(description=description[:2000])
    gen = structured_model or llm_svc.provider.raw_model.with_structured_output(StrategyOutput)
    messages: list[dict] = [{"role": "user", "content": prompt}]

    max_retries = max(0, settings.STRATEGY_GEN_MAX_RETRIES)
    for _attempt in range(max_retries + 1):
        try:
            result = await gen.ainvoke(messages)
            llm_svc.breaker.on_success()
        except Exception as e:  # noqa: BLE001
            llm_svc.breaker.on_failure()
            raise LLMError(f"策略生成失败: {type(e).__name__}: {e}") from e

        if not isinstance(result, StrategyOutput):
            raise LLMError("策略输出 schema 校验失败")

        # 阶段八 8.3：三级校验（语法 + 接口 + 沙箱 dry-run）
        validation = validate_strategy(result.code)
        if validation["valid"]:
            return result

        # 阶段八 8.4：校验失败拼错误信息要求修复，重新生成完整策略
        err_text = _format_errors(validation["errors"])
        logger.warning("strategy validation failed, retrying: %s", err_text[:300])
        messages = [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": f"已生成策略代码：\n```python\n{result.code}\n```"},
            {
                "role": "user",
                "content": "上面的策略代码校验未通过，请修复后重新生成完整策略（code/params/description/strategy_name 全字段）。"
                f"\n校验错误：\n{err_text}",
            },
        ]

    raise LLMError(_RETRY_EXHAUSTED_MSG)

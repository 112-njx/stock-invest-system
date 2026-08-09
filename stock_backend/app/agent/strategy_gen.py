"""策略生成（3.5）：LangChain with_structured_output 生成策略代码 + JSON 参数，schema 校验 + 语法检查。

借鉴 AgentQuant「自然语言→策略代码」+ QuantDinger「模板化策略」思路：约束回测接口 initialize/on_bar，
保证生成的代码可直接入库回测（阶段四引擎）。
"""

import ast
import logging
from typing import Any

from app.schemas.strategy import StrategyOutput
from app.services.llm import LLMError, LLMService

logger = logging.getLogger(__name__)

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
1. 代码必须是合法 Python，只用基础语法与简单数值计算（回测沙箱内运行，禁网络/文件操作）。
2. 给出完整可运行的 initialize 与 on_bar，逻辑自洽。
3. params 用 JSON 结构给出：entry（入场）/ stop_loss（止损）/ take_profit（止盈）/ position（仓位）四组参数，
   值为简洁的 key-value（如 {{"fast": 5, "slow": 20}}）。
4. strategy_name 简洁命名；description 用中文说明策略逻辑；risk_warning 提示主要风险。
5. 只依据用户描述设计，数据不足时在 description 说明假设。

用户交易想法：
{description}
"""


async def generate_strategy(
    description: str,
    llm_svc: LLMService | None = None,
    structured_model: Any | None = None,
) -> StrategyOutput:
    """生成策略。structured_model 供测试注入（默认 provider.raw_model.with_structured_output）。"""
    llm_svc = llm_svc or __import__("app.services.llm", fromlist=["get_llm_service"]).get_llm_service()
    if not llm_svc.available:
        raise LLMError("AI 服务不可用（未配置 DeepSeek API Key），无法生成策略")

    await llm_svc.preflight()
    prompt = _GENERATE_PROMPT.format(description=description[:2000])
    messages = [{"role": "user", "content": prompt}]
    gen = structured_model or llm_svc.provider.raw_model.with_structured_output(StrategyOutput)
    try:
        result = await gen.ainvoke(messages)
        llm_svc.breaker.on_success()
    except Exception as e:  # noqa: BLE001
        llm_svc.breaker.on_failure()
        raise LLMError(f"策略生成失败: {type(e).__name__}: {e}") from e

    if not isinstance(result, StrategyOutput):
        raise LLMError("策略输出 schema 校验失败")
    _validate_code(result.code)
    return result


def _validate_code(code: str) -> None:
    """语法检查（ast.parse）：确保生成的代码可直接入库回测。"""
    if not code or not code.strip():
        raise LLMError("策略代码为空")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise LLMError(f"策略代码语法错误: {e}") from e
    # 粗校验接口函数存在
    funcs = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef,))}
    if "on_bar" not in funcs:
        raise LLMError("策略代码缺少 on_bar 回调函数")

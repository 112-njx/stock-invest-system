"""策略三级校验（阶段八 8.3 + G25 增强）：语法 → 接口 → 沙箱 dry-run。

- 第一级：``ast.parse`` 语法校验（含错误行号）；
- 第二级：接口校验——initialize/on_bar 存在、on_bar 签名为 (bar, context)、无顶层 import；
- 第三级：沙箱 dry-run——用 1 根模拟 K 线在**独立子进程**内跑真实回测引擎，
  施加 CPU 1s / 内存 64MB 限制，捕获运行期异常并回传策略代码行号。

**G25（P1-4b）把第三级从进程内改到子进程**，三点收益：

1. 死循环策略被 terminate，**不会挂住调用方** —— 此前进程内执行会挂住 AI 队列 worker，
   只能等 Celery 硬超时杀进程；
2. 与真实回测**同引擎、同沙箱**，不再是"近似上下文"（原 ``_DryRunContext`` 与真实
   ``BacktestContext`` 在 T+1/费用/持仓语义上并不一致，校验通过不代表回测能跑）；
3. 资源超限策略在**提交回测前**就被拒，而不是跑起来才失败。

返回 ``{"valid": bool, "errors": [{"line": int|None, "message": str}]}``。
"""

import ast
import logging

from app.backtest.engine import BacktestConfig, BacktestError
from app.backtest.runner import StrategyResourceError, StrategyRuntimeError, run_isolated
from app.backtest.sandbox import SandboxError, compile_strategy

logger = logging.getLogger(__name__)

# dry-run 资源限制（G25 规格：CPU 1s / 内存 64MB）
_DRY_RUN_CPU_SECONDS = 1
_DRY_RUN_MEMORY_BYTES = 64 * 1024 * 1024
_DRY_RUN_TIME_BUDGET = 2.0  # 引擎内部时间预算（1 根 bar，正常远低于此）
_DRY_RUN_GRACE = 3.0  # 子进程墙钟宽限：墙钟上限 = 2 + 3 = 5s

_MOCK_BAR = {
    "ts": 0,
    "open": 10.0,
    "high": 11.0,
    "low": 9.0,
    "close": 10.5,
    "volume": 10000,
    "amount": 105000.0,
}


def _check_interface(tree: ast.AST, errors: list[dict]) -> None:
    """第二级：接口校验。"""
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    if "initialize" not in funcs:
        errors.append({"line": None, "message": "缺少 initialize 函数"})
    on_bar = funcs.get("on_bar")
    if on_bar is None:
        errors.append({"line": None, "message": "缺少 on_bar 回调函数"})
        return
    # 引擎按 (bar, context) 位置调用，仅校验参数个数（参数名不影响位置调用）
    args = [a.arg for a in on_bar.args.args]
    if len(args) != 2:
        errors.append(
            {"line": on_bar.lineno, "message": f"on_bar 参数应为 2 个（bar, context），实际 {len(args)} 个"}
        )
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            errors.append({"line": node.lineno, "message": "策略代码禁止 import"})


def _dry_run(code: str, errors: list[dict]) -> None:
    """第三级：沙箱 dry-run —— 独立子进程内用 1 根模拟 K 线跑真实引擎（CPU 1s / 内存 64MB）。

    先做一次进程内编译，把语法/沙箱类错误（SandboxError）直接报出来并省掉一次进程启动；
    编译通过后再进子进程跑，捕获运行期异常与资源超限。
    """
    try:
        compile_strategy(code)
    except SandboxError as e:
        errors.append({"line": None, "message": str(e)})
        return

    try:
        run_isolated(
            code,
            {},
            [dict(_MOCK_BAR)],
            BacktestConfig(time_budget=_DRY_RUN_TIME_BUDGET, period="1d"),
            grace=_DRY_RUN_GRACE,
            cpu_seconds=_DRY_RUN_CPU_SECONDS,
            memory_bytes=_DRY_RUN_MEMORY_BYTES,
        )
    except (StrategyRuntimeError, StrategyResourceError) as e:
        # 策略自身问题（运行期异常 / 超时 / CPU / 内存超限）→ 明确拒绝，带上行号
        errors.append({"line": getattr(e, "line", None), "message": str(e)})
    except BacktestError as e:
        # 既不是策略运行期错误也不是资源超限 → **dry-run 基础设施故障**（子进程起不来、
        # 目标模块无法导入等）。此时**放行**并告警：校验器自己坏了不该挡住用户提交，
        # 运行时隔离（G08 子进程 + 墙钟 terminate）仍是兜底。
        # 实测触发场景：宿主脚本经 `python - <<EOF`（stdin）运行时 spawn 无法重导入 __main__，
        # 会让**所有**策略都"校验不通过"——正是这条兜底避免了整站不可用。
        logger.warning("dry-run infrastructure failure, level-3 check skipped: %s", e)


def validate_strategy(code: str) -> dict:
    """三级校验入口：返回 {"valid": bool, "errors": [{"line", "message"}]}。"""
    errors: list[dict] = []
    if not code or not code.strip():
        return {"valid": False, "errors": [{"line": None, "message": "策略代码为空"}]}

    # 第一级：语法
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"valid": False, "errors": [{"line": e.lineno, "message": f"语法错误: {e.msg}"}]}

    # 第二级：接口
    _check_interface(tree, errors)
    if errors:
        return {"valid": False, "errors": errors}

    # 第三级：沙箱 dry-run
    _dry_run(code, errors)
    return {"valid": not errors, "errors": errors}

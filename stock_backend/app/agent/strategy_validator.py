"""策略生成三级校验（阶段八 8.3）：语法 → 接口 → 沙箱 dry-run。

- 第一级：``ast.parse`` 语法校验（含错误行号）；
- 第二级：接口校验——initialize/on_bar 存在、on_bar 签名为 (bar, context)、无顶层 import；
- 第三级：沙箱 dry-run——用 1 根模拟 K 线在 RestrictedPython 沙箱执行 initialize()+on_bar()，
  捕获 NameError/IndexError/ZeroDivisionError 等运行时异常并提取行号。

返回 ``{"valid": bool, "errors": [{"line": int|None, "message": str}]}``。
"""

import ast
import logging
import traceback

from app.backtest.sandbox import SandboxError, compile_strategy

logger = logging.getLogger(__name__)

_MOCK_BAR = {
    "ts": 0,
    "open": 10.0,
    "high": 11.0,
    "low": 9.0,
    "close": 10.5,
    "volume": 10000,
    "amount": 105000.0,
}


class _DryRunContext:
    """dry-run 用轻量上下文，镜像 BacktestContext 的公开接口（策略可安全调用）。"""

    def __init__(self):
        self.params: dict = {}
        self.cash: float = 1_000_000
        self.pos: int = 0
        self.entry_price: float | None = None
        self.price: float = 10.0
        self.bar_index: int = 0
        self.history: list[dict] = []

    @property
    def closes(self) -> list[float]:
        return [b["close"] for b in self.history]

    @property
    def is_holding(self) -> bool:
        return self.pos > 0

    def buy(self, shares: int | None = None) -> None:
        self.pos += shares or 100

    def sell(self, shares: int | None = None) -> None:
        self.pos = max(0, self.pos - (shares or self.pos))

    def flat(self) -> None:
        self.pos = 0


def _extract_line(exc: BaseException) -> int | None:
    """从异常链中提取策略代码（<string> 编译）的行号，取最内层命中帧。"""
    e: BaseException | None = exc
    while e is not None:
        for frame in reversed(traceback.extract_tb(e.__traceback__)):
            if frame.filename == "<string>" and frame.lineno:
                return frame.lineno
        e = e.__cause__
    return None


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
    """第三级：沙箱 dry-run（1 根模拟 K 线执行 initialize + on_bar）。"""
    try:
        funcs = compile_strategy(code)
    except SandboxError as e:
        errors.append({"line": None, "message": str(e)})
        return
    ctx = _DryRunContext()
    bar = dict(_MOCK_BAR)
    try:
        if "initialize" in funcs:
            funcs["initialize"](ctx)
        funcs["on_bar"](bar, ctx)
    except Exception as e:  # noqa: BLE001
        line = _extract_line(e)
        errors.append({"line": line, "message": f"{type(e).__name__}: {e}"})


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

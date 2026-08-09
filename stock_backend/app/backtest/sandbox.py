"""策略代码安全沙箱（4.1）：RestrictedPython 受限执行。

借鉴 AgentQuant「自然语言→策略代码→沙箱执行」思路：用 RestrictedPython 编译策略代码，
限制危险操作（禁 import / 文件 / 网络 / eval），仅暴露安全内建与策略接口
（initialize(context) / on_bar(bar, context)），策略只能通过 context 触发交易。
"""

import ast
import logging
from types import SimpleNamespace
from typing import Any

from RestrictedPython import compile_restricted_exec, safe_builtins
from RestrictedPython.Guards import (
    guarded_iter_unpack_sequence,
    guarded_unpack_sequence,
    safer_getattr,
)

logger = logging.getLogger(__name__)


class SandboxError(Exception):
    """策略代码编译/安全检查失败（不可重试）。"""


# 策略常用的纯函数内建（safe_builtins 之外补充，均无副作用/网络/IO）
_SAFE_EXTRA_BUILTINS: dict[str, Any] = {
    "min": min,
    "max": max,
    "sum": sum,
    "enumerate": enumerate,
    "any": any,
    "all": all,
    "reversed": reversed,
    "map": map,
    "filter": filter,
    "list": list,
    "dict": dict,
    "set": set,
    "range": range,
    "abs": abs,
    "round": round,
}


def _noop_print(*_args: Any, **_kwargs: Any) -> None:
    """策略内 print 丢弃（避免污染任务 stdout）。"""


def _build_globals() -> dict:
    """构造一份受限全局命名空间（每策略一份，exec 会污染命名空间）。"""
    return {
        "__builtins__": {**safe_builtins, **_SAFE_EXTRA_BUILTINS},
        "_getattr_": safer_getattr,  # 属性访问守卫：拒绝 _ 开头危险属性 / str.format
        "_write_": lambda o: o,  # 允许策略给 context 等普通对象赋值属性
        "_getitem_": lambda o, k: o[k],  # 下标访问
        "_getiter_": iter,
        "_unpack_sequence_": guarded_unpack_sequence,
        "_iter_unpack_sequence_": guarded_iter_unpack_sequence,
        "_print_": lambda _getattr_: SimpleNamespace(_call_print=_noop_print),
        "__name__": "__restricted__",
    }


# 危险内置调用（禁网络/文件/代码执行）——编译期硬拒，即使不在受限内建也会 NameError
_DANGEROUS_BUILTINS = {"open", "eval", "exec", "compile", "__import__", "input", "breakpoint", "globals", "locals", "vars"}


def _reject_imports(code: str) -> None:
    """AST 硬拒 import 语句与危险内置调用（网络/文件/代码执行），编译期拦截更清晰。"""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SandboxError(f"策略代码语法错误: {e}") from e
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise SandboxError("策略代码禁止 import")
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and f.id in _DANGEROUS_BUILTINS:
                raise SandboxError(f"策略代码禁止调用危险内建: {f.id}")


def compile_strategy(code: str) -> dict[str, Any]:
    """编译策略代码，返回 {'initialize': fn?, 'on_bar': fn}（受限可调用函数）。

    - AST 检查禁 import；
    - RestrictedPython 编译检查危险语法；
    - 在受限命名空间 exec，提取 initialize/on_bar。
    编译失败抛 SandboxError（不可重试）。
    """
    if not code or not code.strip():
        raise SandboxError("策略代码为空")
    _reject_imports(code)

    res = compile_restricted_exec(code)
    if res.errors:
        raise SandboxError(f"策略代码受限检查失败: {'; '.join(res.errors)}")

    glb = _build_globals()
    try:
        exec(res.code, glb)
    except Exception as e:  # noqa: BLE001
        raise SandboxError(f"策略代码加载失败: {type(e).__name__}: {e}") from e

    funcs: dict[str, Any] = {}
    on_bar = glb.get("on_bar")
    if not callable(on_bar):
        raise SandboxError("策略代码缺少 on_bar 回调函数")
    funcs["on_bar"] = on_bar
    init = glb.get("initialize")
    if callable(init):
        funcs["initialize"] = init
    return funcs

"""统一响应结构 {code, msg, data}：成功 code=0；业务失败 code 非 0。"""

from typing import Any


def ok(data: Any = None, msg: str = "ok") -> dict:
    return {"code": 0, "msg": msg, "data": data}


def fail(code: int = 1, msg: str = "error", data: Any = None) -> dict:
    return {"code": code, "msg": msg, "data": data}

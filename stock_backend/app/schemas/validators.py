"""G30：用户可控文本字段的通用校验。

- 控制字符禁用：C0/C1 控制字符（保留 \\t \\n \\r 供多行文本），
  防日志注入、终端转义序列注入、以及绕过前端渲染的畸形输入。
- 长度上限：由各字段的 Field(max_length=...) 声明，此处只提供可复用的注解类型。
- URL 校验：只允许 http/https（禁 javascript:/data: 等可执行协议）。
"""

import re
from typing import Annotated

from pydantic import AfterValidator

# C0/C1 控制字符，放行 \t(09) \n(0a) \r(0d)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

# 允许的 URL 协议（相对路径 / 站内路径也放行）
_URL_RE = re.compile(r"^(https?://|/|#)", re.IGNORECASE)


def _reject_control_chars(v: str | None) -> str | None:
    if v is None:
        return None
    if _CONTROL_CHARS_RE.search(v):
        raise ValueError("包含非法控制字符")
    return v


def _validate_http_url(v: str | None) -> str | None:
    """只允许 http(s):// 或站内相对路径；拒绝 javascript:/data:/vbscript: 等。"""
    if v and not _URL_RE.match(v):
        raise ValueError("仅支持 http/https 链接或站内路径")
    return v


def _strip_or_none(v: str | None) -> str | None:
    """空白串归一为 None（避免存 "" 与 None 两种空值语义）。"""
    if v is None:
        return None
    v = v.strip()
    return v or None


# ---- 可复用注解类型 ----

SafeText = Annotated[str, AfterValidator(_reject_control_chars)]
"""单行/多行用户文本：禁控制字符。长度上限由字段的 Field(max_length=) 声明。"""

SafeTextOptional = Annotated[str | None, AfterValidator(_strip_or_none), AfterValidator(_reject_control_chars)]
"""可选文本：先 strip（空白→None）再禁控制字符。"""

HttpUrlText = Annotated[str, AfterValidator(_validate_http_url), AfterValidator(_reject_control_chars)]
"""URL 字段：仅 http/https/相对路径，且禁控制字符。"""

HttpUrlTextOptional = Annotated[
    str | None,
    AfterValidator(_strip_or_none),
    AfterValidator(_validate_http_url),
    AfterValidator(_reject_control_chars),
]

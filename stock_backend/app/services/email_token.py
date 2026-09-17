"""邮件验证/密码重置专用 JWT token。

与 access token 独立：
- 使用不同 secret（派生自 JWT_SECRET_KEY + 用途后缀），防止 access token 被用于验证/重置
- 携带 type 字段（verify_email / reset_password），防止跨用途滥用
- 不同过期时间（验证 10min / 重置 1h）
"""

from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings

_settings = get_settings()

# 派生密钥：基于主密钥 + 用途后缀，避免与 access token 共享签名
_VERIFY_SECRET = ""
_RESET_SECRET = ""


def _get_verify_secret() -> str:
    global _VERIFY_SECRET
    if not _VERIFY_SECRET:
        _VERIFY_SECRET = _settings.JWT_SECRET_KEY + "|email_verify"
    return _VERIFY_SECRET


def _get_reset_secret() -> str:
    global _RESET_SECRET
    if not _RESET_SECRET:
        _RESET_SECRET = _settings.JWT_SECRET_KEY + "|password_reset"
    return _RESET_SECRET


def create_verify_token(user_id: int, email: str) -> str:
    """创建邮箱验证 token（10 分钟有效）。"""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "verify_email",
        "exp": now + timedelta(minutes=10),
        "iat": now,
    }
    return jwt.encode(payload, _get_verify_secret(), algorithm=_settings.JWT_ALGORITHM)


def verify_email_token(token: str) -> tuple[int, str] | None:
    """校验邮箱验证 token，返回 (user_id, email) 或 None。"""
    try:
        payload = jwt.decode(token, _get_verify_secret(), algorithms=[_settings.JWT_ALGORITHM])
        if payload.get("type") != "verify_email":
            return None
        return int(payload["sub"]), payload["email"]
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        return None


def create_reset_token(user_id: int, email: str) -> str:
    """创建密码重置 token（1 小时有效）。"""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "reset_password",
        "exp": now + timedelta(hours=1),
        "iat": now,
    }
    return jwt.encode(payload, _get_reset_secret(), algorithm=_settings.JWT_ALGORITHM)


def verify_reset_token(token: str) -> tuple[int, str] | None:
    """校验密码重置 token，返回 (user_id, email) 或 None。"""
    try:
        payload = jwt.decode(token, _get_reset_secret(), algorithms=[_settings.JWT_ALGORITHM])
        if payload.get("type") != "reset_password":
            return None
        return int(payload["sub"]), payload["email"]
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        return None

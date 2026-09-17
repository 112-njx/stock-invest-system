"""安全工具：密码 bcrypt 哈希 + JWT 签发/校验（借鉴 TradingAgents-CN token 机制）。

生产注意：JWT_SECRET_KEY 必须在 .env 覆盖为强随机值，否则 token 可被伪造。
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from app.core.config import get_settings

_settings = get_settings()


def hash_password(password: str) -> str:
    """bcrypt 哈希（自动加盐）。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码；哈希非法时按不通过处理，不抛异常。"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    """签发 JWT（HS256，sub=user_id，含过期时间）。"""
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(UTC) + timedelta(minutes=_settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _settings.JWT_SECRET_KEY, algorithm=_settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """解析 JWT 返回 user_id；无效/过期返回 None。"""
    try:
        payload = jwt.decode(token, _settings.JWT_SECRET_KEY, algorithms=[_settings.JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        return None


# ---------- Cookie 安全工具（G01：为 G19 refresh token Cookie 预留）----------

def set_access_token_cookie(response, token: str, max_age: int | None = None) -> None:
    """设置 access token HttpOnly Cookie（Secure/SameSite 从配置读取）。

    G01 阶段仅预留工具函数，G19 登录/刷新流程正式启用。
    """
    response.set_cookie(
        key=_settings.ACCESS_TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_settings.COOKIE_SECURE,
        samesite=_settings.COOKIE_SAMESITE,
        path="/",
        max_age=max_age,
    )


def clear_access_token_cookie(response) -> None:
    """清除 access token Cookie。"""
    response.delete_cookie(
        key=_settings.ACCESS_TOKEN_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=_settings.COOKIE_SECURE,
        samesite=_settings.COOKIE_SAMESITE,
    )

"""安全工具：密码 bcrypt 哈希 + JWT 签发/校验 + 双 token + 黑名单。

生产注意：JWT_SECRET_KEY 必须在 .env 覆盖为强随机值，否则 token 可被伪造。
G19：access token 15min JWT(jti+iat) + refresh token 7d HttpOnly Cookie + 轮换/复用检测/黑名单。
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from app.core.config import get_settings

_settings = get_settings()


# ---------- 密码 ----------

def hash_password(password: str) -> str:
    """bcrypt 哈希（自动加盐）。"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码；哈希非法时按不通过处理，不抛异常。"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# ---------- Access Token（JWT，15min，含 jti/iat）----------

def create_access_token(user_id: int) -> str:
    """签发 access token JWT（HS256，sub=user_id，jti=唯一ID，iat=签发时间，exp=15min）。"""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "exp": now + timedelta(minutes=_settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": now,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, _settings.JWT_SECRET_KEY, algorithm=_settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """解析 JWT 返回 user_id；无效/过期返回 None（向后兼容，不检查黑名单）。"""
    try:
        payload = jwt.decode(token, _settings.JWT_SECRET_KEY, algorithms=[_settings.JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        return None


def decode_access_token_full(token: str) -> dict | None:
    """解析 JWT 返回完整 payload（含 sub/jti/iat/exp）；无效/过期返回 None。"""
    try:
        return jwt.decode(token, _settings.JWT_SECRET_KEY, algorithms=[_settings.JWT_ALGORITHM])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        return None


# ---------- Refresh Token（随机字符串，7d，HttpOnly Cookie）----------

def generate_refresh_token() -> str:
    """生成 refresh token（48 字节 URL 安全随机字符串，~64 字符）。"""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """SHA-256 哈希 refresh token（只存哈希，明文不落盘）。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------- Token 黑名单（Redis）----------

def blacklist_access_token(jti: str, remaining_seconds: int) -> None:
    """将 access token 的 jti 加入 Redis 黑名单（登出/踢出/改密时调用）。"""
    if remaining_seconds <= 0:
        return
    try:
        from app.utils.redis_client import get_redis_client
        r = get_redis_client()
        r.set(f"token_blacklist:{jti}", "1", ex=remaining_seconds)
    except Exception:  # noqa: BLE001
        pass  # Redis 不可用时 best-effort（不影响主流程）


def is_access_token_blacklisted(jti: str) -> bool:
    """检查 access token jti 是否在黑名单中。"""
    try:
        from app.utils.redis_client import get_redis_client
        r = get_redis_client()
        return r.exists(f"token_blacklist:{jti}") > 0
    except Exception:  # noqa: BLE001
        return False  # Redis 不可用时默认放行（降级，不影响可用性）


def blacklist_refresh_token(token_hash: str, remaining_seconds: int) -> None:
    """将 refresh token 哈希加入 Redis 黑名单（轮换时旧 token 入黑名单）。"""
    if remaining_seconds <= 0:
        return
    try:
        from app.utils.redis_client import get_redis_client
        r = get_redis_client()
        r.set(f"refresh_blacklist:{token_hash}", "1", ex=remaining_seconds)
    except Exception:  # noqa: BLE001
        pass


def is_refresh_token_blacklisted(token_hash: str) -> bool:
    """检查 refresh token 哈希是否在黑名单中（True = 已被轮换过，再用即复用攻击）。"""
    try:
        from app.utils.redis_client import get_redis_client
        r = get_redis_client()
        return r.exists(f"refresh_blacklist:{token_hash}") > 0
    except Exception:  # noqa: BLE001
        return False


# ---------- Cookie 安全工具 ----------

def set_refresh_token_cookie(response, token: str, max_age: int | None = None) -> None:
    """设置 refresh token HttpOnly Cookie（Secure/SameSite 从配置读取）。"""
    response.set_cookie(
        key=_settings.REFRESH_TOKEN_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=_settings.COOKIE_SECURE,
        samesite=_settings.COOKIE_SAMESITE,
        path="/api/v1/auth",  # 仅 auth 路径携带（减小攻击面）
        max_age=max_age,
    )


def clear_refresh_token_cookie(response) -> None:
    """清除 refresh token Cookie。"""
    response.delete_cookie(
        key=_settings.REFRESH_TOKEN_COOKIE_NAME,
        path="/api/v1/auth",
        httponly=True,
        secure=_settings.COOKIE_SECURE,
        samesite=_settings.COOKIE_SAMESITE,
    )


def set_access_token_cookie(response, token: str, max_age: int | None = None) -> None:
    """设置 access token HttpOnly Cookie（G01 预留，当前未启用）。"""
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

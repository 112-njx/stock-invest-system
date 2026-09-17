"""导出文件下载签名 token（G17）。

与 access token 独立签名（派生密钥 + type 字段），短时效（默认 30 分钟），
携带 task_id + user_id，下载端点校验两者匹配才允许读取文件，防越权下载。
"""

from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import get_settings

_settings = get_settings()

_SECRET: str = ""


def _get_secret() -> str:
    global _SECRET
    if not _SECRET:
        _SECRET = _settings.JWT_SECRET_KEY + "|export_download"
    return _SECRET


def create_download_token(user_id: int, task_id: int) -> str:
    """签发下载 token（默认 30 分钟有效）。"""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "task_id": task_id,
        "type": "export_download",
        "exp": now + timedelta(minutes=_settings.EXPORT_DOWNLOAD_TOKEN_MINUTES),
        "iat": now,
    }
    return jwt.encode(payload, _get_secret(), algorithm=_settings.JWT_ALGORITHM)


def verify_download_token(token: str) -> tuple[int, int] | None:
    """校验下载 token，返回 (user_id, task_id)；无效/过期返回 None。"""
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[_settings.JWT_ALGORITHM])
        if payload.get("type") != "export_download":
            return None
        return int(payload["sub"]), int(payload["task_id"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        return None

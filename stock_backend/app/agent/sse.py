"""SSE 事件基础设施（阶段五）：delta 断点续传缓存 + 错误帧标准化。

- delta 缓存：`chat_delta:{conversation_id}`（List，TTL 600s，最多最近 100 条）
- 完成标记：`chat_done:{conversation_id}`（String，TTL 600s，存 done 事件）
- 错误帧：统一 ``{"type":"error","code":...,"message":...,"retryable":...,"retry_after"?}``
"""

import json
import logging

from app.core.config import get_settings
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
settings = get_settings()


# ---- 错误码枚举（阶段五 5.3）----
class ErrorCode:
    NETWORK_ERROR = "NETWORK_ERROR"  # 网络错误，可重试
    RATE_LIMITED = "RATE_LIMITED"  # 限流，带 retry_after
    TOKEN_INVALID = "TOKEN_INVALID"  # 用户 token 无效，不可重试
    TOKEN_QUOTA = "TOKEN_QUOTA"  # 余额不足，不可重试
    CONTENT_FILTERED = "CONTENT_FILTERED"  # 内容违规，不可重试
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"  # 服务端 LLM 不可用，可重试
    TIMEOUT = "TIMEOUT"  # 超时，可重试


_RETRYABLE_CODES = {ErrorCode.NETWORK_ERROR, ErrorCode.RATE_LIMITED, ErrorCode.PROVIDER_UNAVAILABLE, ErrorCode.TIMEOUT}


def build_error_event(code: str, message: str, retryable: bool | None = None, retry_after: int | None = None) -> dict:
    """构造标准化 SSE 错误帧。"""
    ev = {
        "type": "error",
        "code": code,
        "message": message,
        "retryable": retryable if retryable is not None else code in _RETRYABLE_CODES,
    }
    if retry_after is not None:
        ev["retry_after"] = retry_after
    return ev


# ---- delta 断点续传缓存 ----
def _delta_key(conversation_id: int) -> str:
    return f"chat_delta:{conversation_id}"


def _done_key(conversation_id: int) -> str:
    return f"chat_done:{conversation_id}"


def clear_delta_cache(conversation_id: int) -> None:
    """新消息开始时清空旧缓存。"""
    try:
        get_redis_client().delete(_delta_key(conversation_id), _done_key(conversation_id))
    except Exception:  # noqa: BLE001
        logger.warning("clear delta cache failed conv=%s", conversation_id, exc_info=True)


def cache_delta(conversation_id: int, event: dict) -> None:
    """追加一条 delta（含 seq）到缓存，仅保留最近 SSE_DELTA_CACHE_MAX 条。"""
    try:
        r = get_redis_client()
        key = _delta_key(conversation_id)
        pipe = r.pipeline()
        pipe.rpush(key, json.dumps(event, ensure_ascii=False))
        pipe.ltrim(key, -settings.SSE_DELTA_CACHE_MAX, -1)
        pipe.expire(key, settings.SSE_DELTA_CACHE_TTL)
        pipe.execute()
    except Exception:  # noqa: BLE001
        logger.warning("cache delta failed conv=%s", conversation_id, exc_info=True)


def cache_done(conversation_id: int, event: dict) -> None:
    """缓存 done 事件（供断线续传补发 message_id）。"""
    try:
        get_redis_client().set(_done_key(conversation_id), json.dumps(event, ensure_ascii=False), ex=settings.SSE_DELTA_CACHE_TTL)
    except Exception:  # noqa: BLE001
        logger.warning("cache done failed conv=%s", conversation_id, exc_info=True)


def read_deltas_after(conversation_id: int, last_seq: int) -> list[dict] | None:
    """返回 seq>last_seq 的 delta 事件列表；缓存已过期/不可用返回 None。"""
    try:
        r = get_redis_client()
        key = _delta_key(conversation_id)
        raw = r.lrange(key, 0, -1)
        if not raw:
            # 空：区分「无 delta」与「缓存已过期」
            return [] if r.exists(key) else None
        out = []
        for item in raw:
            ev = json.loads(item)
            if ev.get("seq", 0) > last_seq:
                out.append(ev)
        return out
    except Exception:  # noqa: BLE001
        logger.warning("read deltas failed conv=%s", conversation_id, exc_info=True)
        return None


def read_done(conversation_id: int) -> dict | None:
    """读取缓存的 done 事件（未完成或过期返回 None）。"""
    try:
        raw = get_redis_client().get(_done_key(conversation_id))
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None

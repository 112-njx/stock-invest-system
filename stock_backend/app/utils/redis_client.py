"""Redis 客户端：模块级单例（线程安全），供 API 缓存与 Celery 任务复用。"""

import redis

from app.core.config import get_settings

_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    """获取全局 Redis 客户端（懒加载单例）。"""
    global _client
    if _client is None:
        _client = redis.Redis.from_url(get_settings().REDIS_URL, decode_responses=True)
    return _client

"""Redis 客户端：模块级单例（线程安全），供 API 缓存与 Celery 任务复用。

G11（P1-2b）高可用
------------------
`REDIS_SENTINEL_HOSTS` 非空时走 **Sentinel**：客户端向 Sentinel 询问当前主节点地址并连接，
主从切换后自动重连到新主（`Sentinel.master_for` 的连接池会在下一次取连接时重新解析主节点，
**无需重启应用**）。

**超时参数必须显式收紧**：Sentinel 在故障转移窗口内可能暂时答不出主节点地址，
`Sentinel()` 默认会重试多次；这里把 socket_timeout 设小，避免故障期间请求线程被长时间挂住
（宁可快速失败交由上层降级，也不要拖垮整个 API）。

降级：`REDIS_SENTINEL_HOSTS` 为空时行为与改造前**完全一致**（直连 `REDIS_URL`），
本地单实例开发零影响。
"""

import logging

import redis
from redis.sentinel import Sentinel

from app.core.config import get_settings

logger = logging.getLogger(__name__)
_client: redis.Redis | None = None


def _build_client() -> redis.Redis:
    """按配置构造 Redis 客户端：Sentinel 优先，未配置则直连。"""
    settings = get_settings()
    hosts = [h.strip() for h in (settings.REDIS_SENTINEL_HOSTS or "").split(",") if h.strip()]
    if settings.REDIS_SENTINEL_ENABLED and not hosts:
        logger.warning(
            "REDIS_SENTINEL_ENABLED=true but REDIS_SENTINEL_HOSTS is empty; "
            "falling back to direct REDIS_URL connection"
        )
    if not hosts:
        return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

    sentinel_hosts: list[tuple[str, int]] = []
    for item in hosts:
        host, _, port = item.partition(":")
        sentinel_hosts.append((host, int(port or 26379)))
    sentinel_kwargs: dict = {"socket_timeout": settings.REDIS_SENTINEL_SOCKET_TIMEOUT}
    if settings.REDIS_SENTINEL_PASSWORD:
        sentinel_kwargs["password"] = settings.REDIS_SENTINEL_PASSWORD
    sentinel = Sentinel(
        sentinel_hosts,
        sentinel_kwargs=sentinel_kwargs,
        socket_timeout=settings.REDIS_SENTINEL_SOCKET_TIMEOUT,
    )
    # db 号仍从 REDIS_URL 取：Sentinel 只负责发现主节点，不改变库编号
    db = redis.Redis.from_url(settings.REDIS_URL).connection_pool.connection_kwargs.get("db", 0)
    logger.info(
        "redis sentinel enabled: master=%s hosts=%s db=%s", settings.REDIS_SENTINEL_MASTER, sentinel_hosts, db
    )
    return sentinel.master_for(settings.REDIS_SENTINEL_MASTER, db=db, decode_responses=True)


def get_redis_client() -> redis.Redis:
    """获取全局 Redis 客户端（懒加载单例）。"""
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def reset_redis_client() -> None:
    """丢弃单例（仅供测试；生产代码无调用方）。"""
    global _client
    _client = None

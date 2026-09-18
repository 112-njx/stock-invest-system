"""回测并发配额与队列繁忙判定（G08 · P1-4a）。

两道上限
--------
1. **per-user 并发**：同一用户同时运行的回测数 ≤ ``BACKTEST_MAX_CONCURRENT_PER_USER``，超出返回 429；
2. **全局队列**：回测队列积压 ≥ ``BACKTEST_QUEUE_BUSY_THRESHOLD`` 时直接拒绝并提示"队列繁忙"，
   避免任务排进去干等（全局并发上限本身由 Celery worker 数控制）。

为什么用 ZSET 而不是 INCR 计数器
--------------------------------
简单计数器（``INCR`` / ``DECR``）在 worker 崩溃、任务丢失、进程被 SIGKILL 时**会永久泄漏**，
把用户锁死在"已达并发上限"且无法自愈。这里用 **ZSET**（member=一次性槽位 token，score=占用时间戳）：

- 每次取配额前按 ``BACKTEST_QUOTA_STALE_SECONDS`` 清理过期槽位 → **自愈**；
- 取配额用 **Lua 脚本**原子执行「清理 → 判数 → 加入」，避免并发请求同时通过检查（check-then-act 竞态）。

失败策略：**fail-open**。Redis 不可用时放行并告警 —— 此时 Celery broker 同样不可用，
任务本就入不了队（``create_backtest`` 有对应的入队失败处理），不应因配额检查而阻塞用户。
"""

import logging
import time

from app.core.config import get_settings
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
_settings = get_settings()

BACKTEST_QUEUE = "backtest"

# KEYS[1]=key  ARGV[1]=now  ARGV[2]=stale_seconds  ARGV[3]=limit  ARGV[4]=member  ARGV[5]=ttl
# 返回 {是否获得(1/0), 操作后的运行数}
_ACQUIRE_LUA = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', tonumber(ARGV[1]) - tonumber(ARGV[2]))
local n = redis.call('ZCARD', KEYS[1])
if n >= tonumber(ARGV[3]) then
  return {0, n}
end
redis.call('ZADD', KEYS[1], tonumber(ARGV[1]), ARGV[4])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[5]))
return {1, n + 1}
"""


def _key(user_id: int) -> str:
    return f"backtest_running:{user_id}"


def acquire(user_id: int, token: str) -> tuple[bool, int]:
    """尝试占用一个并发配额（原子）。

    返回 ``(是否获得, 操作后该用户的运行数)``。Redis 不可用时 **fail-open** 返回 ``(True, -1)``。
    """
    limit = _settings.BACKTEST_MAX_CONCURRENT_PER_USER
    stale = _settings.BACKTEST_QUOTA_STALE_SECONDS
    try:
        result = get_redis_client().eval(
            _ACQUIRE_LUA, 1, _key(user_id), time.time(), stale, limit, token, stale + 60
        )
        granted, running = int(result[0]), int(result[1])
        return bool(granted), running
    except Exception as e:  # noqa: BLE001 —— fail-open，见模块 docstring
        logger.warning("backtest quota acquire failed (fail-open) user=%s: %s", user_id, e)
        return True, -1


def release(user_id: int, token: str) -> None:
    """释放配额。幂等：槽位不存在时 ZREM 为空操作，可安全重复调用。"""
    try:
        get_redis_client().zrem(_key(user_id), token)
    except Exception as e:  # noqa: BLE001 —— 释放失败由 stale 清理兜底
        logger.warning("backtest quota release failed user=%s: %s", user_id, e)


def running_count(user_id: int) -> int:
    """该用户当前运行中的回测数（先清理过期槽位）。Redis 不可用返回 -1。"""
    stale = _settings.BACKTEST_QUOTA_STALE_SECONDS
    try:
        r = get_redis_client()
        key = _key(user_id)
        r.zremrangebyscore(key, "-inf", time.time() - stale)
        return int(r.zcard(key))
    except Exception as e:  # noqa: BLE001
        logger.warning("backtest quota count failed user=%s: %s", user_id, e)
        return -1


def queue_depth(queue: str = BACKTEST_QUEUE) -> int:
    """回测队列积压任务数（Celery 在 Redis 上以 list 承载队列）。Redis 不可用返回 -1。"""
    try:
        return int(get_redis_client().llen(queue))
    except Exception as e:  # noqa: BLE001
        logger.warning("backtest queue depth failed: %s", e)
        return -1


def is_queue_busy(queue: str = BACKTEST_QUEUE) -> bool:
    """队列是否繁忙（积压达阈值）。Redis 不可用时 fail-open 返回 False。"""
    depth = queue_depth(queue)
    if depth < 0:
        return False
    return depth >= _settings.BACKTEST_QUEUE_BUSY_THRESHOLD

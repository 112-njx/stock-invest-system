"""跨 API/Worker 进程的外部行情请求节流与每日预算。"""

import time
from datetime import datetime

from app.core.config import get_settings
from app.utils.redis_client import get_redis_client

_SCRIPT = """
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
if count >= tonumber(ARGV[2]) then return -1 end
if redis.call('SET', KEYS[2], '1', 'NX', 'PX', ARGV[1]) == false then return 0 end
redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], 172800)
return 1
"""


def limits() -> tuple[int, int]:
    settings = get_settings()
    redis = get_redis_client()
    values = redis.mget('provider:limit:interval', 'provider:limit:budget')
    return (int(values[0] or settings.PROVIDER_MIN_INTERVAL_SECONDS),
            int(values[1] or settings.PROVIDER_DAILY_BUDGET))


def acquire(provider: str) -> None:
    """在真正发起网络请求前调用；Redis 失联时停止外部请求，避免失控。"""
    from app.data_providers.base import ProviderError

    try:
        interval, budget = limits()
        redis = get_redis_client()
        day = datetime.now(get_settings().tz).strftime('%Y%m%d')
        for _ in range(300):
            result = redis.eval(_SCRIPT, 2, f'provider:used:{provider}:{day}',
                                f'provider:slot:{provider}', interval * 1000, budget)
            if result == 1:
                return
            if result == -1:
                raise ProviderError(f'{provider} daily request budget exhausted')
            time.sleep(0.1)
        raise ProviderError(f'{provider} request throttle timeout')
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError('provider throttle unavailable') from exc


def usage() -> dict:
    from app.data_providers.factory import get_provider

    redis = get_redis_client()
    day = datetime.now(get_settings().tz).strftime('%Y%m%d')
    interval, budget = limits()
    return {'day': day, 'interval_seconds': interval, 'daily_budget': budget,
            'providers': [{'name': p['name'], 'used': int(redis.get(f"provider:used:{p['name']}:{day}") or 0),
                           'health': p} for p in get_provider().health()]}

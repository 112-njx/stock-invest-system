"""Optional AkShare history in Redis; StockDB persistence is unaffected."""
import json
import logging
from dataclasses import asdict
from datetime import UTC, datetime

from app.data_providers.base import KlineBar, ProviderError
from app.data_providers.factory import get_provider
from app.models.symbol import Symbol
from app.services import market_policy
from app.utils.market_cache import as_utc
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
FIRST = datetime(2000, 1, 1, tzinfo=UTC)
TTL = 3600


def _key(symbol_id, period, revision=None):
    revision = market_policy.read()['revision'] if revision is None else revision
    return f'source-history:v1:{revision}:{symbol_id}:{period}'


def cached(symbol_id, period):
    try:
        raw = get_redis_client().get(_key(symbol_id, period))
        if raw is not None:
            return [KlineBar(**{**row, 'ts': datetime.fromisoformat(row['ts'])}) for row in json.loads(raw)]
    except Exception:
        logger.debug('source history cache unavailable', exc_info=True)
    return None


def store(symbol_id, period, bars, revision=None):
    try:
        rows = [{**asdict(bar), 'ts': bar.ts.isoformat()} for bar in bars]
        get_redis_client().set(_key(symbol_id, period, revision), json.dumps(rows), ex=TTL if bars else 30)
    except Exception:
        logger.warning('source history cache write failed', exc_info=True)


def _load(db, symbol_id, period, *, refresh=False, revision=None, external_only=False):
    if not refresh:
        bars = cached(symbol_id, period)
        if bars is not None:
            return bars
    symbol = db.get(Symbol, symbol_id)
    if symbol is None:
        return []
    from app.services.sync_service import _provider_params
    code, asset = _provider_params(symbol)
    provider = get_provider()
    if not market_policy.akshare_enabled():
        return []
    if not any((not external_only or p.name != 'stockdb') and p.can_fetch_kline(asset, period)
               for p in provider._active_providers()):
        return []
    bars, confirmed_empty = provider.fetch_kline_checked(code, period, FIRST, datetime.now(UTC), asset, external_only=external_only)
    if not bars and not confirmed_empty:
        raise ProviderError(f'{symbol.name} {period} 数据源查询失败，请检查 RD 7899 / SDK 7900 服务')
    # SDK may label an unfinished week/month more than once. Keep the last
    # native record, using exactly the same rule as the persistent repository.
    def identity(bar):
        day = bar.ts.date()
        return day.isocalendar()[:2] if period == '1w' else (day.year, day.month) if period == '1mon' else bar.ts
    bars = list({identity(bar): bar for bar in sorted(bars, key=lambda bar: bar.ts)}.values())
    store(symbol_id, period, bars, revision)
    return bars


def load(db, symbol_id, period, *, refresh=False, external_only=False):
    revision = market_policy.read()['revision']
    if not refresh:
        rows = cached(symbol_id, period)
        if rows is not None:
            return rows
    lock = None
    try:
        lock = get_redis_client().lock(_key(symbol_id, period, revision) + ':lock', timeout=240, blocking_timeout=185)
        acquired = lock.acquire()
    except Exception:
        lock = None
        acquired = True  # Redis outage must not make source reads impossible.
    if not acquired:
        raise ProviderError('本地行情仍在准备，请稍后重试')
    try:
        return _load(db, symbol_id, period, refresh=refresh, revision=revision, external_only=external_only)
    finally:
        if lock is not None:
            try:
                lock.release()
            except Exception:
                logger.debug('source lock release failed', exc_info=True)


def window(db, symbol_id, period, start, end, limit=1000, offset=0):
    bars = [bar for bar in load(db, symbol_id, period) if as_utc(start) <= as_utc(bar.ts) <= as_utc(end)]
    return bars[offset:offset + limit]

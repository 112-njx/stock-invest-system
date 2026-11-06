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
FIRST = datetime(1900, 1, 1, tzinfo=UTC)
TTL = 3600


def _key(symbol_id, period, revision=None):
    revision = market_policy.read()['revision'] if revision is None else revision
    return f'source-history:v2:{revision}:{symbol_id}:{period}'


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
        if not get_redis_client().set(_key(symbol_id, period, revision), json.dumps(rows), ex=TTL if bars else 30):
            raise RuntimeError('Redis did not acknowledge history storage')
    except Exception as exc:
        raise ProviderError('AkShare 历史缓存写入失败，任务未完成') from exc


def _load(db, symbol_id, period, *, refresh=False, revision=None):
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
    if not any(p.name != 'stockdb' and p.can_fetch_kline(asset, period)
               for p in provider._active_providers()):
        return []
    bars, confirmed_empty = provider.fetch_kline_checked(code, period, FIRST, datetime.now(UTC), asset, external_only=True)
    if not bars and not confirmed_empty:
        raise ProviderError(f'{symbol.name} {period} 数据源查询失败，请检查 RD 7899 / SDK 7900 服务')
    if any(bar.source != 'akshare' for bar in bars):
        raise ProviderError('AkShare 缓存拒绝接收其他来源的历史数据')
    # Keep the last native record for an unfinished week/month, matching the
    # persistent repository without locally aggregating any OHLC values.
    def identity(bar):
        day = bar.ts.date()
        return day.isocalendar()[:2] if period == '1w' else (day.year, day.month) if period == '1mon' else bar.ts
    bars = list({identity(bar): bar for bar in sorted(bars, key=lambda bar: bar.ts)}.values())
    store(symbol_id, period, bars, revision)
    return bars


def load(db, symbol_id, period, *, refresh=False):
    """Worker-only preparation. Query endpoints must use cached/window instead."""
    revision = market_policy.read()['revision']
    if not refresh:
        rows = cached(symbol_id, period)
        if rows is not None:
            return rows
    lock = None
    try:
        lock = get_redis_client().lock(_key(symbol_id, period, revision) + ':lock', timeout=240, blocking_timeout=185)
        acquired = lock.acquire()
    except Exception as exc:
        raise ProviderError('AkShare 历史缓存不可用，任务未完成') from exc
    if not acquired:
        raise ProviderError('本地行情仍在准备，请稍后重试')
    try:
        return _load(db, symbol_id, period, refresh=refresh, revision=revision)
    finally:
        if lock is not None:
            try:
                lock.release()
            except Exception:
                logger.debug('source lock release failed', exc_info=True)


def window(db, symbol_id, period, start, end, limit=1000, offset=0, *, latest=False):
    bars = [bar for bar in (cached(symbol_id, period) or []) if as_utc(start) <= as_utc(bar.ts) <= as_utc(end)]
    if latest:
        stop = max(0, len(bars) - offset)
        return bars[max(0, stop - limit):stop]
    return bars[offset:offset + limit]

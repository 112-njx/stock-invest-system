"""Latest local daily records, independent of the realtime snapshot pipeline."""
import json
import logging
from datetime import UTC, datetime
from app.data_providers.stockdb import StockDBProvider
from app.repositories import kline_repo
from app.utils.redis_client import get_redis_client
from app.services.market_policy import akshare_enabled

logger = logging.getLogger(__name__)


def stored_quote(db, sym, bars=None):
    if bars is None:
        bars = kline_repo.latest_bars(db, '1d', sym.id, limit=2)
    if not bars:
        return {}
    latest = bars[-1]
    close = float(latest.close)
    previous = float(bars[-2].close) if len(bars) > 1 else None
    return dict(price=close, pre_close=previous, change=close-previous if previous else None,
                change_pct=(close/previous-1)*100 if previous else None,
                amplitude=(float(latest.high)-float(latest.low))/previous*100 if previous else None,
                open=float(latest.open), high=float(latest.high), low=float(latest.low),
                volume=int(latest.volume)*100, amount=float(latest.amount),
                updated_at=latest.ts.isoformat(), data_date=latest.ts.date().isoformat(),
                source=latest.source)


def quotes(db, symbols):
    result = []
    for sym in symbols:
        item = dict(symbol_id=sym.id, code=sym.code, name=sym.name, type=sym.type,
                    source='stockdb', extra={})
        try:
            if sym.type in {'stock', 'etf'}:
                key = f'local-quote:v1:{sym.code}'
                try:
                    raw = get_redis_client().get(key)
                except Exception:
                    raw = None
                if raw:
                    row = json.loads(raw)
                else:
                    rows = StockDBProvider().query('vals', '日k', k1=f'key:{sym.code}', k2='all:', num=-1)
                    row = rows[-1] if rows else None
                    if row:
                        try:
                            get_redis_client().set(key, json.dumps(row), ex=30)
                        except Exception:
                            pass
                if row:
                    close, previous = row['close'], row.get('pre_close')
                    item.update(price=close, pre_close=previous,
                                change=round(close-previous, 3 if sym.type == 'etf' else 2) if previous is not None else None,
                                change_pct=row.get('pct_chg'), open=row.get('open'), high=row.get('high'),
                                low=row.get('low'), volume=row.get('volume'), amount=row.get('amount'),
                                turnover=row.get('turnover'), amplitude=row.get('amplitude'),
                                updated_at=datetime.strptime(str(row['date']), '%Y%m%d').replace(tzinfo=UTC).isoformat(),
                                data_date=datetime.strptime(str(row['date']), '%Y%m%d').date().isoformat())
                    item['extra'] = {k: row.get(k) for k in ('vol_ratio','is_st','total_share','float_share',
                                                            'total_mv','float_mv','pe_ttm','pb')}
                    item['extra'].update(market_cap=row.get('total_mv'), pe=row.get('pe_ttm'))
            else:
                item.update(stored_quote(db, sym))
        except Exception as exc:
            logger.warning('local daily quote unavailable code=%s: %s', sym.code, exc)
            item['extra']['data_status'] = 'local_unavailable'
        if item.get('price') is None and sym.type in {'stock', 'etf'}:
            if akshare_enabled():
                item.update(stored_quote(db, sym))
        result.append(item)
    return result

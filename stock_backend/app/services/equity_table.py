"""Local A-share table with bounded shared snapshots and background refresh."""
import json
import math
import logging
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timedelta
from threading import Lock, Thread
from time import monotonic
from app.data_providers.stockdb import StockDBProvider
from app.services.stock_search_directory import get_directory
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
_error = ''
_state = None
_checked = 0
_lock = Lock()
_running = False
_KEY = 'equity-table:v2'
FIELDS = ('open','high','low','close','volume','amount','turnover','amplitude','total_mv',
          'float_mv','total_share','float_share','pe_ttm','pb','vol_ratio')


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def valid_close(row, code):
    return (isinstance(row, dict) and row.get('code') == code
            and isinstance(row.get('date'), int)
            and number(row.get('close')) is not None and row['close'] > 0)


def returns(history, factors, baseline, latest):
    if (not baseline or not latest or number(baseline[1]) is None or baseline[1] <= 0
            or number(latest[1]) is None or latest[1] <= 0 or baseline[0] > latest[0]):
        return None
    dates = [d for d, _ in factors]
    def factor(d):
        at = bisect_right(dates, d)
        return factors[at-1][1] if at else 1
    return (latest[1] * factor(latest[0]) / (baseline[1] * factor(baseline[0])) - 1) * 100


def build():
    provider = StockDBProvider()
    directory = get_directory()
    stocks = directory['items']
    # Use the directory only to bound the lookback, never as a latest-date ceiling.
    # The batch scans include every local date after that bound, even if a directory
    # refresh or one individual stock is lagging behind the market.
    anchor = max(int(stock['latest_date']) for stock in stocks)
    start = int((datetime.strptime(str(anchor),'%Y%m%d')-timedelta(days=65)).strftime('%Y%m%d'))
    codes = {stock['code'] for stock in stocks}
    history = defaultdict(dict)
    for prefix in ('0','3','6','8','9'):
        rows = provider.query('vals','日k',k1='qz:'+prefix,k2=f'fwd:{start},99991231',ap='get.date,code,close')
        for record in rows:
            if not isinstance(record, (list, tuple)) or len(record) != 3:
                continue
            day, code, close = record
            if code in codes and isinstance(day, int) and number(close) is not None and close > 0:
                history[code][day] = close
    if not history:
        raise ValueError('本地股票库没有有效收盘数据')
    latest = max(day for timeline in history.values() for day in timeline)
    year = latest // 10000
    baseline = {}
    prior_end = (year-1)*10000+1231
    for prefix in ('0','3','6','8','9'):
        rows = provider.query('vals','日k',k1='qz:'+prefix,
                              k2=f'fwd:{(year-1)*10000+1201},{prior_end}',ap='get.date,code,close')
        for record in rows:
            if not isinstance(record, (list, tuple)) or len(record) != 3:
                continue
            day, code, close = record
            if code in codes and number(close) is not None and close > 0:
                if code not in baseline or day > baseline[code][0]:
                    baseline[code] = (day,close)
    factors = defaultdict(list)
    for key, cumulative in provider.query('get','复权*',ap='get.cum'):
        _, code, day = key.split(':')
        if number(cumulative) and cumulative > 0: factors[code].append((int(day),cumulative))
    for timeline in factors.values(): timeline.sort()
    boards = [b for _,b in provider.query('get','板块*') if b.get('category')=='申万一级']
    industries = {}
    for b in sorted(boards,key=lambda b:(len(b['symbols']),b['code'])):
        for code in b['symbols']: industries.setdefault(code,b['name'])
    latest_rows = {r['code']:r for r in provider.query('vals','日k',k1='all:',k2=f'key:{latest}') if isinstance(r,dict)}
    items = []
    for stock in stocks:
        code = stock['code']
        row = latest_rows.get(code)
        if not valid_close(row, code):
            records = provider.query('vals','日k',k1='key:'+code,k2='all:',num=-22)
            valid_records = [r for r in records if valid_close(r, code) and r['date'] <= latest]
            row = max(valid_records, key=lambda r:r['date'], default=None)
            for record in valid_records:
                history[code][record['date']] = record['close']
        if not row: continue
        data = {k:number(row.get(k)) for k in FIELDS}
        previous, close = number(row.get('pre_close')), data['close']
        data.update(code=code,name=row.get('name') or stock['name'],market=stock['market'],
                    industry=industries.get(code,''),data_date=row['date'],pe=number(row.get('pe')),
                    change=close-previous if close is not None and previous else None,
                    change_pct=(close/previous-1)*100 if close is not None and previous else None)
        if data['turnover'] is None and data['float_share'] and data['volume'] is not None:
            data['turnover'] = data['volume']/data['float_share']*100
        if data['amplitude'] is None and previous and data['high'] is not None and data['low'] is not None:
            data['amplitude'] = (data['high']-data['low'])/previous*100
        timeline = sorted((d,c) for d,c in history[code].items() if d <= row['date'])
        last = (row['date'],close)
        for n in (5,10,20):
            data['return_'+str(n)] = returns(timeline,factors[code],timeline[-n-1] if len(timeline)>n else None,last)
        # Newly listed equities start at their first available session in the current year.
        base = baseline.get(code)
        if base is None:
            prior = provider.query('vals','日k',k1='key:'+code,k2=f'fwd:19000101,{prior_end}',num=-1)
            if prior and valid_close(prior[-1],code):
                base=(prior[-1]['date'],prior[-1]['close'])
        if base is None:
            first = provider.query('vals','日k',k1='key:'+code,k2='all:',num=1)
            if first and valid_close(first[0],code) and first[0]['date']//10000 == year: base=(first[0]['date'],first[0]['close'])
        data['return_ytd'] = returns(timeline,factors[code],base,last)
        items.append(data)
    return dict(items=items,date=latest,industries=sorted(set(industries.values())),source='stockdb',
                static_pe_available=any(x['pe'] is not None for x in items))


def _refresh():
    global _state, _checked, _running, _error
    try:
        candidate = build()
        _state = candidate
        _error = ''
        try: get_redis_client().set(_KEY,json.dumps(candidate,ensure_ascii=False),ex=7*86400)
        except Exception: pass
    except Exception:
        logger.exception('Local equity table refresh failed')
        _error = '本地股票数据读取失败，请确认数据源服务可用'
    finally:
        with _lock:
            _checked = monotonic()
            _running = False


def snapshot():
    global _state, _running
    with _lock:
        if _state is None:
            try:
                saved = get_redis_client().get(_KEY)
                if saved: _state = json.loads(saved)
            except Exception: pass
        if not _running and (_checked == 0 or monotonic()-_checked > (300 if _state else 30)):
            _running = True
            Thread(target=_refresh,name='equity-table-refresh',daemon=True).start()
        if _state is None: return dict(items=[],industries=[],loading=_running,error=_error)
        return {**_state,'loading':False,'refreshing':_running,'error':_error}

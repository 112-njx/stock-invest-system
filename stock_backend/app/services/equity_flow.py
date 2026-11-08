"""Latest local money-flow view, with same-session ratios and complete windows."""
import json
import logging
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timedelta
from threading import Lock, Thread
from time import monotonic
from app.data_providers.stockdb import StockDBProvider
from app.services import equity_table
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
FIELDS = ('main_net','jumbo_net','big_net','mid_net','small_net')
_KEY = 'equity-flow:v3'
_lock = Lock()
_state = None
_running = False
_checked = 0
_error = ''


def aggregate(quotes, history, amounts, trading_dates=None):
    dates = sorted(set(trading_dates) if trading_dates is not None else {d for records in history.values() for d in records})
    items = []
    for quote in quotes:
        code = quote['code']
        records = history.get(code, {})
        item = {k: quote[k] for k in ('code','name','market','industry','close','change_pct','data_date')}
        item.update({k:None for k in (*FIELDS,'main_ratio','flow_date','main_5','main_10','main_20')})
        if records:
            day = max(records)
            row = records[day]
            item.update({k:equity_table.number(row.get(k)) for k in FIELDS})
            item['flow_date'] = str(day)
            amount = amounts.get((code,day))
            if item['main_net'] is not None and amount is not None and amount > 0:
                item['main_ratio'] = item['main_net']/amount*100
            end = bisect_right(dates,day)
            for n in (5,10,20):
                window = dates[max(0,end-n):end]
                values = [equity_table.number(records.get(d,{}).get('main_net')) for d in window]
                if len(values)==n and all(v is not None for v in values):
                    item['main_'+str(n)] = sum(values)
        items.append(item)
    return items


def calendar_ranges(start, history):
    """Include fallback windows without scanning the years between old and recent data."""
    ranges = [(start, 99991231)]
    for records in history.values():
        if records and min(records) < start:
            ranges.append((min(records), max(records)))
    merged = []
    for left, right in sorted(ranges):
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
        else:
            merged.append((left, right))
    return merged


def build():
    quotes = equity_table.snapshot()
    if quotes.get('loading') or not quotes.get('items'):
        raise ValueError('行情快照尚未就绪，资金流向稍后重试')
    provider = StockDBProvider()
    start = int((datetime.strptime(str(quotes['date']),'%Y%m%d')-timedelta(days=65)).strftime('%Y%m%d'))
    by_code = defaultdict(dict)
    codes = {q['code'] for q in quotes['items']}
    for prefix in ('0','3','6','8','9'):
        records = provider.query('vals','资金流',k1='qz:'+prefix,k2=f'fwd:{start},99991231')
        for row in records:
            if isinstance(row,dict) and row.get('code') in codes and isinstance(row.get('date'),int):
                by_code[row['code']][row['date']] = row
    # Retain the last local record for stocks suspended or missing from the recent window.
    for code in codes-by_code.keys():
        records = provider.query('vals','资金流',k1='key:'+code,k2='all:',num=-20)
        for row in records:
            if isinstance(row,dict) and row.get('code')==code and isinstance(row.get('date'),int):
                by_code[code][row['date']] = row
    amounts = {(q['code'],q['data_date']):q.get('amount') for q in quotes['items']}
    required_dates = {max(records) for records in by_code.values() if records}
    for day in required_dates:
        needed = {code for code,records in by_code.items() if records and max(records)==day and (code,day) not in amounts}
        if not needed: continue
        rows = provider.query('vals','日k',k1='all:',k2=f'key:{day}',ap='get.code,amount')
        for row in rows:
            if isinstance(row,(list,tuple)) and len(row)==2 and row[0] in needed:
                amounts[(row[0],day)] = equity_table.number(row[1])
    trading_dates = set()
    for left, right in calendar_ranges(start, by_code):
        for prefix in ('0','3','6','8','9'):
            rows = provider.query('vals','日k',k1='qz:'+prefix,k2=f'fwd:{left},{right}',ap='get.date,code')
            for row in rows:
                if isinstance(row,(list,tuple)) and len(row)==2 and row[1] in codes and isinstance(row[0],int):
                    trading_dates.add(row[0])
    items = aggregate(quotes['items'],by_code,amounts,trading_dates)
    return dict(items=items,industries=quotes['industries'],date=quotes['date'],
                flow_date=max(required_dates) if required_dates else None,
                missing=sum(r['flow_date'] is None for r in items),source='stockdb')


def _refresh():
    global _state,_running,_checked,_error
    try:
        candidate = build()
        _state = candidate
        _error = ''
        try: get_redis_client().set(_KEY,json.dumps(candidate,ensure_ascii=False),ex=7*86400)
        except Exception: pass
    except Exception as exc:
        logger.warning('Local money-flow snapshot refresh failed: %s',exc)
        _error = '资金流数据暂未就绪，正在等待本地数据源；已有数据会继续保留'
    finally:
        with _lock:
            _checked = monotonic()
            _running = False


def snapshot():
    global _state,_running
    with _lock:
        if _state is None:
            try:
                raw = get_redis_client().get(_KEY)
                if raw: _state=json.loads(raw)
            except Exception: pass
        if not _running and (_checked==0 or monotonic()-_checked > (300 if _state else 5)):
            _running=True
            Thread(target=_refresh,name='equity-flow-refresh',daemon=True).start()
        return {**(_state or dict(items=[],industries=[])), 'loading':_state is None,
                'refreshing':_running,'error':_error}

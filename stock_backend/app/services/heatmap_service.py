"""Bounded, close-only SW1 market-cap change snapshots from local RD."""
import json
import math
from datetime import datetime
from hashlib import sha256
from threading import Lock
from time import time
from zoneinfo import ZoneInfo

from redis.exceptions import RedisError

from app.services import stockdb_service as rd
from app.utils.redis_client import get_redis_client

_lock = Lock()
_cached = None
_checked = 0.0
_candidate = ("", 0.0)
_key = "market-heatmap:v1:" + sha256(rd.get_settings().STOCKDB_URL.encode()).hexdigest()[:12]


def valid(row):
    return len(row) == 7 and all(isinstance(row[i], (int, float)) and math.isfinite(row[i])
                                 and row[i] > 0 for i in (0, 3, 4, 5))


def aggregate(boards, days, date, previous):
    """Resolve overlapping legacy memberships to the smaller, more specific board."""
    owners = {}
    for board in sorted(boards, key=lambda b: (len(b['symbols']), b['code'])):
        for code in board['symbols']:
            owners.setdefault(code, board['code'])
    groups = []
    missing = zero = 0
    for board in boards:
        children = []
        for code in dict.fromkeys(board['symbols']):
            if owners[code] != board['code']:
                continue
            row, before = days[date].get(code), days[previous].get(code)
            if not row or not before or not valid(row) or not valid(before):
                missing += 1
                continue
            delta = row[5] - before[5]
            change = (row[3] / row[4] - 1) * 100
            zero += delta == 0
            children.append(dict(code=code, name=row[2] or code, close=row[3], change=round(change, 4),
                                 totalMv=row[5], deltaMv=delta, value=abs(delta)))
        value = sum(x['value'] for x in children)
        prior = sum(days[previous][x['code']][5] for x in children)
        groups.append(dict(code=board['code'], name=board['name'], value=value, children=children,
                           change=round(sum(x['deltaMv'] for x in children) / prior * 100, 4) if prior else 0,
                           up=sum(x['change'] > 0 for x in children), down=sum(x['change'] < 0 for x in children)))
    return dict(date=date, previousDate=previous, boards=groups, missing=missing, zero=zero,
                duplicates=sum(len(set(b['symbols'])) for b in boards)-len(owners),
                count=sum(len(b['children']) for b in groups), total=len(owners))


def load(now):
    with rd._client() as client:
        boards = [b for _, b in rd._rd(client, 'get', '板块*') if b.get('category') == '申万一级']
        if not boards:
            raise rd.StockDBError('本地数据源没有申万一级行业目录')
        today = int(now.strftime('%Y%m%d'))
        dates = sorted(int(k.rsplit(':', 1)[-1]) for k in rd._rd(client, 'keys', '日k', k1='key:600519', k2='all:'))
        dates = [d for d in dates if d < today or (d == today and (now.hour, now.minute) >= (15, 30))][-4:]
        if len(dates) < 2:
            raise rd.StockDBError('缺少两个已收盘交易日的数据')
        days = {d: {} for d in dates}
        for prefix in ('0', '3', '6', '8', '9'):
            rows = rd._rd(client, 'vals', '日k', k1='qz:'+prefix,
                          k2=f'fwd:{dates[0]},{dates[-1]}', ap='get.date,code,name,close,pre_close,total_mv,float_mv')
            for row in rows:
                if len(row) == 7 and row[0] in days:
                    days[row[0]][row[1]] = row
    members = {s for b in boards for s in b['symbols']}
    for index in range(len(dates)-1, 0, -1):
        date, previous = dates[index], dates[index-1]
        baseline = {s for s in members if s in days[previous] and valid(days[previous][s])}
        available = {s for s in baseline if s in days[date] and valid(days[date][s])}
        # Allows isolated suspensions but rejects a partially imported session.
        if baseline and len(available) / len(baseline) >= .995:
            return aggregate(boards, days, date, previous)
    raise rd.StockDBError('最新收盘数据覆盖不足，等待本地数据同步完成')


def snapshot():
    global _cached, _checked, _candidate
    with _lock:
        if _cached and time() - _checked < 60:
            return _cached
        redis = get_redis_client()
        if _cached is None:
            try:
                saved = redis.get(_key)
                if saved:
                    _cached = json.loads(saved)
            except (RedisError, ValueError):
                pass
        try:
            now = datetime.now(ZoneInfo('Asia/Shanghai'))
            result = load(now)
            if _cached and result['date'] < _cached['date']:
                _cached = {**_cached, 'warning': '本地数据日期回退，保留上次收盘快照'}
                return _cached
            signature = sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
            if result['date'] == int(now.strftime('%Y%m%d')):
                # Two identical observations at least one minute apart before publishing today's close.
                if _candidate[0] != signature:
                    _candidate = (signature, time())
                if time() - _candidate[1] < 60:
                    if _cached:
                        _cached = {**_cached, 'warning': '当日数据校验中，继续展示上一份收盘快照'}
                        return _cached
                    # On cold start, build the preceding session instead.
                    result = load(now.replace(hour=0, minute=0))
            result['updatedAt'] = now.isoformat()
            result['version'] = sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()[:20]
            _cached = result
            try:
                redis.set(_key, json.dumps(result, ensure_ascii=False), ex=30*86400)
            except RedisError:
                pass
        except Exception as exc:
            if _cached is None:
                raise rd.StockDBError(str(exc)) from exc
            _cached = {**_cached, 'warning': '数据源暂不可用或覆盖不足，保留上次收盘快照'}
            return _cached
        finally:
            _checked = time()
        return _cached

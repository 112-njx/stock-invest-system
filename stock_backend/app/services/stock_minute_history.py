"""Bounded raw intraday history with per-session volume-weighted prices."""
from datetime import date, datetime, timedelta
import math
from .stockdb_service import _client, _rd


def finite(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def normalize(rows):
    output = []
    day = None
    volume = amount = 0.0
    complete = True
    for row in sorted(rows, key=lambda r: r.get('date', 0)):
        stamp = str(row.get('date', ''))
        clock = stamp[8:14]
        if len(stamp) != 14 or not ('093000' <= clock <= '113000' or '130000' <= clock <= '150000'):
            continue
        price = row.get('close')
        if not finite(price) or price <= 0:
            continue
        if day != stamp[:8]:
            day = stamp[:8]
            volume = amount = 0.0
            complete = True
        v, a = row.get('volume'), row.get('amount')
        if finite(v) and v >= 0 and finite(a) and a >= 0:
            volume += v
            amount += a
        else:
            complete = False
        output.append(dict(date=int(stamp), price=price,
                           volume=v if finite(v) and v >= 0 else None,
                           average=amount / volume if complete and volume > 0 else None))
    return output


def load(code, start=None, end=None):
    with _client() as client:
        latest = _rd(client, 'keys', '分钟k', k1=f'key:{code}', k2='all:', num=-1)
        if not latest:
            return dict(rows=[], latest=None, start=None, end=None, previous=None, baseline_date=None)
        latest_day = datetime.strptime(latest[-1].rsplit(':', 1)[-1][:8], '%Y%m%d').date()
        end = end or latest_day
        start = start or end - timedelta(days=20)
        if start > end or (end - start).days > 45:
            raise ValueError('开始日期不得晚于结束日期，每次最多查询45天')
        rows = _rd(client, 'vals', '分钟k', k1=f'key:{code}',
                   k2=f'fwd:{start:%Y%m%d}000000,{end:%Y%m%d}235959')
        normalized = normalize([r for r in rows if r.get('code') == code])
        baseline_date = normalized[-1]['date'] // 1000000 if normalized else None
        daily = _rd(client, 'vals', '日k', k1=f'key:{code}', k2=f'qz:{baseline_date}') if baseline_date else []
    previous = next((r.get('pre_close') for r in daily if r.get('code') == code), None)
    return dict(rows=normalized, baseline_date=baseline_date,
                latest=int(latest_day.strftime('%Y%m%d')), start=start.isoformat(), end=end.isoformat(),
                previous=previous if finite(previous) and previous > 0 else None)

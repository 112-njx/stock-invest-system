"""Bounded per-stock money-flow history; metadata never implies market-wide coverage."""
from datetime import date, datetime, timedelta
from app.data_providers.stockdb import StockDBProvider
from app.services.equity_flow import FIELDS
from app.services.equity_table import number


def day(value):
    return int(value.strftime('%Y%m%d'))


def trading_dates(provider, code, start, end):
    dates=set()
    # Union the selected stock and two independently stored exchange sessions.
    for symbol in dict.fromkeys((code,'000001','600519')):
        for key in provider.query('keys','日k',k1='key:'+symbol,k2=f'fwd:{start},{end}'):
            dates.add(int(key.rsplit(':',1)[-1]))
    return dates


def load(code, start=None, end=None):
    provider=StockDBProvider()
    first=provider.query('keys','资金流',k1='key:'+code,k2='all:',num=1)
    last=provider.query('keys','资金流',k1='key:'+code,k2='all:',num=-1)
    if not first or not last:
        return dict(code=code,coverage=None,latest=None,totals={str(n):None for n in (5,10,20)},rows=[],start=start.isoformat() if start else None,end=end.isoformat() if end else None)
    first_day=int(first[0].rsplit(':',1)[-1]);last_day=int(last[-1].rsplit(':',1)[-1])
    latest_date=datetime.strptime(str(last_day),'%Y%m%d').date()
    end=end or latest_date
    start=start or end-timedelta(days=65)
    if start>end or (end-start).days>366:
        raise ValueError('查询日期范围须按先后排列，且每次不超过366天')
    def read(left,right):
        return {r['date']:{'date':r['date'],**{k:number(r.get(k)) for k in FIELDS}}
                for r in provider.query('vals','资金流',k1='key:'+code,k2=f'fwd:{left},{right}')
                if isinstance(r,dict) and r.get('code')==code and isinstance(r.get('date'),int)}
    records=read(day(start),day(end))
    dates=trading_dates(provider,code,day(start),day(end))|set(records)
    rows=[records.get(d,{'date':d,**{k:None for k in FIELDS}}) for d in sorted(dates)]
    recent_start=day(latest_date-timedelta(days=65))
    recent=records if day(start)==recent_start and day(end)==last_day else read(recent_start,last_day)
    sessions=sorted(trading_dates(provider,code,recent_start,last_day)|set(recent))
    totals={}
    for n in (5,10,20):
        values=[recent.get(d,{}).get('main_net') for d in sessions[-n:]]
        totals[str(n)]=sum(values) if len(values)==n and all(v is not None for v in values) else None
    return dict(code=code,coverage=dict(start=str(first_day),end=str(last_day)),latest=recent.get(last_day),
                totals=totals,rows=rows,start=start.isoformat(),end=end.isoformat())

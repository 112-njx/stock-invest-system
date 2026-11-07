"""Read-only live API matrix plus full warmup inputs for an independent SDK oracle."""
import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
from urllib.request import urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'stock_backend'))
from app.repositories import kline_repo
from app.services import market_service, indicator_policy, market_policy
from app.utils.db import get_session
from app.utils.market_cache import kline_bar_to_dict


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8081')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    timings=[]
    def get(path,params=None):
        begun=time.perf_counter()
        with urlopen(args.url+'/api/v1/'+path+('?' + urlencode(params) if params else ''),timeout=90) as response:
            body=response.read();value=json.loads(body)
        assert value['code']==0,value.get('msg')
        timings.append(dict(path=path,period=(params or {}).get('period'),ms=round((time.perf_counter()-begun)*1000,2),bytes=len(body)))
        return value['data']
    definitions=get('indicators/catalog')['indicators'];assert len(definitions)==41
    technical=[d for d in definitions if d['key'] not in ('volume','amount')]
    index=dict(members=[dict(code='600519',weight=3),dict(code='300502',weight=1)],weighting='equal',base=1000,start='2025-01-01')
    controls={d['key']:{'cross':True} for d in technical if d.get('cross')}
    custom={}
    for d in technical:
        if d['key']=='ma':custom['ma']={'periods':[7,20,60,120,250,10000]};continue
        if d['key']=='zhishu':continue
        value={p['key']:(.25 if p['key']=='a' else 2.5) if p['type']=='number' else max(2,min(9,p['default']-1)) for p in d['parameters']}
        if d.get('cross'):value['cross']=True
        if d.get('input_fields'):value['field']='volume' if d['placement']=='panel' else 'open'
        custom[d['key']]=value
    custom['macd'].update(fast=7,slow=21,signal=5)
    custom['dfma'].update(n1=5,n2=21,m=6);custom['xsii'].update(n=104,m=5)
    cases=[];datasets={}
    with get_session() as db:
        symbol_id=market_service.resolve_symbol_id(db,'300308')
        for period in ['1d','1w','1mon','15m']:
            # Use the same selected source and complete warmup history, then
            # compare the API independently against raw native functions.
            latest=kline_repo.latest_bars(db,period,symbol_id,limit=40)
            assert len(latest)>=32,(period,'local history missing')
            start,end=latest[-32].ts,latest[-1].ts
            bars=kline_repo.get_bars(db,period,symbol_id,datetime.min.replace(tzinfo=UTC),end,
                limit=100000,source_window=(start,end),latest=False)
            datasets[period]=[kline_bar_to_dict(b) for b in bars]
            for phase in ['default','custom']:
                params={**(controls if phase=='default' else custom),'zhishu':{**index,**({'weighting':'custom','base':2000} if phase=='custom' else {})}}
                q=dict(symbol='300308',period=period,names=','.join(d['key'] for d in technical),params=json.dumps(params),start=start.isoformat(),end=end.isoformat())
                rows=get('indicators',q);assert len(rows)==32,(period,phase,len(rows))
                tail=get('indicators',{**q,'start':rows[-5]['ts']})
                assert tail==rows[-5:],(period,phase,'history paging drift')
                repeat=get('indicators',q);assert repeat==rows,(period,phase,'repeat changed values')
                cases.append(dict(period=period,phase=phase,params=params,rows=rows))
                print(period,phase,'39 indicators, 32 bars, paging and repeat OK',flush=True)
    output=dict(symbol='300308',definitions=technical,datasets=datasets,cases=cases,
                policy=dict(indicators=indicator_policy.read(),market=market_policy.read()),timings=timings)
    (args.out/'api-matrix.json').write_text(json.dumps(output,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print('API matrix written; 8 cases × 39 indicators × 32 bars, plus 16 paging/repeat checks')


if __name__=='__main__':main()

"""Run inside the SDK container: compare live API matrix to raw SDK functions.

This deliberately does not call the application indicator adapter or registry.
"""
import argparse
from datetime import UTC, datetime
import inspect
import json
import math
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


def main():
    parser=argparse.ArgumentParser();parser.add_argument('file',type=Path)
    parser.add_argument('--sdk-dir',default='/opt/stockdb/pybao');args=parser.parse_args()
    sys.path.insert(0,args.sdk_dir)
    import stock_sdk
    if os.environ.get('STOCKDB_READER') == 'managed':
        from market_data_sdk import install
        install(stock_sdk)
    else:
        stock_sdk.init(host='127.0.0.1',port=7899,warm=False)
    from zhibiao import zb, BATCH_CROSS, ZHISHU, _load_rows
    matrix=json.loads(args.file.read_text(encoding='utf-8'));checks=0;nulls=0
    def ts(value):
        time=datetime.fromisoformat(value)
        return (time.replace(tzinfo=UTC) if time.tzinfo is None else time).timestamp()
    for case in matrix['cases']:
        rows=matrix['datasets'][case['period']];indices={r['ts']:i for i,r in enumerate(rows)}
        for d in matrix['definitions']:
            key=d['key'];options=case['params'].get(key,{})
            expected={}
            if key=='zhishu':
                codes=[m['code'] for m in options['members']]
                end=datetime.fromtimestamp(ts(rows[-1]['ts']),UTC)
                stamp=end.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d%H%M%S') if case['period'] in {'1m','5m','15m','30m','60m'} else end.strftime('%Y%m%d')
                arrays=list(_load_rows(codes,'1M' if case['period']=='1mon' else case['period'],options['start'].replace('-',''),stamp,'qfq'))
                if options['weighting']=='custom':arrays[8]=[options['members'][i]['weight'] for i in arrays[0]]
                raw=ZHISHU(*arrays,method=2 if options['weighting']=='custom' else 1,base=float(options['base']))
                values={}
                for i,day in enumerate(raw[0]):
                    s=str(day);time=datetime.strptime(s,'%Y%m%d%H%M%S' if len(s)==14 else '%Y%m%d').replace(tzinfo=ZoneInfo('Asia/Shanghai') if len(s)==14 else UTC)
                    values[time.timestamp()]=(raw[4][i],raw[8][i])
                expected={'zhishu_close':[values.get(ts(r['ts']),(None,None))[0] for r in rows],
                          'zhishu_count':[values.get(ts(r['ts']),(None,None))[1] for r in rows]}
            elif key=='ma':
                for n in options.get('periods',[5,10,20,30]):expected['ma'+str(n)]=zb.MA([r['close'] for r in rows],n)
            elif key=='volume':
                expected['volume']=[r['volume'] for r in rows]
                for n in (5,10):expected[f'volume_ma{n}']=zb.MA(expected['volume'],n)
            elif key=='amount':
                expected['amount']=[r['amount'] for r in rows]
            else:
                native=getattr(zb,key.upper());signature=list(inspect.signature(native).parameters.values())
                count=len(d['inputs']);inputs=[]
                for p in signature[:count]:
                    field='volume' if p.name=='vol' else p.name
                    if field in ('s','close') and d.get('input_fields'):field=options.get('field','close')
                    inputs.append([r[field] for r in rows])
                # The public MACD contract predates the SDK and intentionally
                # calls short/long/m "fast/slow/signal". Resolve that explicit
                # alias without reusing the production positional adapter.
                aliases={'short':'fast','long':'slow','m':'signal'} if key=='macd' else {}
                chosen={p.name:options.get(aliases.get(p.name,p.name),p.default if p.default is not inspect.Parameter.empty else next(x['default'] for x in d['parameters'] if x['key']==p.name)) for p in signature[count:]}
                raw=native(*inputs,**chosen);columns=raw if isinstance(raw,tuple) else [raw]
                expected=dict(zip(d['native_outputs'],columns,strict=True))
                if options.get('cross'):
                    cross=BATCH_CROSS([key],[list(chosen.values())],[0]*len(rows),list(range(len(rows))),*[[r[f] for r in rows] for f in ('open','high','low','close','volume')],False)
                    expected[key+'_cross']=cross[3][cross[2].index('cross')]
            for actual in case['rows']:
                i=indices[actual['ts']]
                for field,values in expected.items():
                    native=values[i];target=float(native) if native is not None and math.isfinite(native) else None
                    if target is None:
                        nulls+=1;assert actual[field] is None,(case['period'],case['phase'],key,field,'null changed')
                    else:assert math.isclose(actual[field],target,rel_tol=1e-12,abs_tol=1e-9),(case['period'],case['phase'],key,field,actual[field],target)
                    checks+=1
        print(case['period'],case['phase'],'raw native comparison OK',flush=True)
    print(json.dumps(dict(native_value_checks=checks,null_checks=nulls,cases=len(matrix['cases']))))


if __name__=='__main__':main()

"""Measure a maximum-size index alongside an uncached ordinary SDK request."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

CODES='600000 600036 600519 601318 601398 601939 601288 601988 600900 600276 000001 000002 000333 000651 000858 002415 002594 300308 300502 300750'.split()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8081')
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--ma-period',type=int,default=173)
    args=parser.parse_args();results=[]
    def call(period,name,params):
        start=time.perf_counter()
        url=args.url+'/api/v1/indicators?'+urlencode(dict(symbol='300308',period=period,names=name,params=json.dumps(params),limit=5))
        try:
            with urlopen(url,timeout=90) as response:status=response.status;body=json.load(response)
        except HTTPError as error:
            status=error.code
            raw=error.read().decode('utf-8',errors='replace')
            try:body=json.loads(raw)
            except ValueError:body={'msg':raw[:160]}
        except (URLError,TimeoutError) as error:
            status=0;body={'msg':str(error)}
        result=dict(period=period,name=name,status=status,ms=round(1000*(time.perf_counter()-start),2),rows=len(body.get('data') or []))
        if status!=200:result['message']=body.get('msg')
        return result
    for period in ['1d','15m']:
        with ThreadPoolExecutor(2) as pool:
            composite=pool.submit(call,period,'zhishu',{'zhishu':dict(members=[dict(code=c,weight=1) for c in CODES],weighting='equal',base=1000,start='2025-01-01')})
            time.sleep(.15)
            normal=pool.submit(call,period,'ma',{'ma':{'periods':[args.ma_period,args.ma_period+1]}})
            for result in (normal.result(),composite.result()):
                results.append(result);print(json.dumps(result,ensure_ascii=False),flush=True)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    if any(r['status']!=200 for r in results):raise SystemExit('Index load blocked or failed an ordinary SDK request')
    if any(r['name']=='ma' and r['ms']>=5000 for r in results):raise SystemExit('Ordinary SDK requests exceeded the five-second isolation budget')


if __name__=='__main__':main()

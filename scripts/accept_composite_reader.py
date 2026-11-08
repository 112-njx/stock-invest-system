"""Compare bounded member readers to the unmodified SDK batch loader."""
import argparse
import math
import sys
import time
from accept_indicator_load import CODES
from stockdb_sdk_bridge import load_composite_arrays


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sdk-dir',default='/opt/stockdb/pybao')
    parser.add_argument('--start',default='20261102');parser.add_argument('--end',default='20261105')
    parser.add_argument('--verify',action='store_true');parser.add_argument('--workers',type=int,default=4)
    parser.add_argument('--members',default=','.join(CODES))
    parser.add_argument('--timeout',type=int,default=25);parser.add_argument('--progress',action='store_true');args=parser.parse_args()
    sys.path.insert(0,args.sdk_dir)
    from zhibiao import _load_rows, ZHISHU
    codes=args.members.split(',')
    start=time.perf_counter()
    progress=(lambda i,n:print(f'{codes[i]}: {n} bars at {time.perf_counter()-start:.3f}s',flush=True)) if args.progress else None
    actual=load_composite_arrays(args.sdk_dir,codes,'15m',args.start,args.end,timeout=args.timeout,max_workers=args.workers,progress=progress,use_cache=False)
    elapsed=time.perf_counter()-start
    assert len(actual[0])>0
    print(f'{len(codes)}-member SDK reader: {len(actual[0])} rows, {elapsed:.3f}s',flush=True)
    if args.verify:
        expected=_load_rows(codes,'15m',args.start,args.end,'qfq')
        from collections import Counter
        print('Member rows actual/SDK:',dict(Counter(actual[0])),dict(Counter(expected[0])),flush=True)
        checks=0
        for a,b in zip(actual,expected,strict=True):
            assert len(a)==len(b)
            for x,y in zip(a,b,strict=True):
                assert x==y or (math.isnan(x) and math.isnan(y)),(x,y)
                checks+=1
        assert ZHISHU(*actual)==ZHISHU(*expected)
        print(f'Exact SDK batch equivalence: {checks} input values plus complete native index output',flush=True)


if __name__=='__main__':main()

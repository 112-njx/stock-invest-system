"""Compare the old and managed readers against the same mounted data version."""
import argparse
import hashlib
import json
from time import monotonic
from urllib.parse import urlencode
from urllib.request import urlopen


def read(base, path, **params):
    with urlopen(base + path + ('?' + urlencode(params) if params else ''), timeout=185) as response:
        return json.load(response)


def digest(value):
    def normalize(item):
        if isinstance(item, float) and item.is_integer():
            return int(item)
        if isinstance(item, list):
            return [normalize(v) for v in item]
        if isinstance(item, dict):
            return {k: normalize(v) for k, v in item.items()}
        return item

    return hashlib.sha256(json.dumps(normalize(value), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def samples(rd, sdk):
    def query(cmd, table, **params):
        return read(rd, '/', cmd=cmd, t=table, json=1, **params)

    date = query('keys', '日k', k1='key:600519', k2='all:', num=-1)[0].rsplit(':', 1)[1]
    for name, cmd, table, params in (
        ('directory', 'get', '股票代码', {}),
        ('retired', 'vals', '退市*', {}),
        ('boards', 'get', '板块*', {}),
        ('factors', 'get', '复权*', {'ap': 'get.cum'}),
        ('daily_latest', 'vals', '日k', {'k1': 'key:600519', 'k2': 'all:', 'num': -20}),
        ('daily_market', 'vals', '日k', {'k1': 'all:', 'k2': 'key:' + date, 'ap': 'get.code,close,volume'}),
        ('daily_window', 'vals', '日k', {'k1': 'qz:60051', 'k2': 'fwd:20261001,' + date}),
        ('minutes', 'vals', '分钟k', {'k1': 'key:600519', 'k2': 'qz:' + date}),
        ('etf_minutes', 'vals', '分钟k', {'k1': 'key:510300', 'k2': 'qz:' + date}),
        ('flows', 'vals', '资金流', {'k1': 'key:600519', 'k2': 'all:', 'num': -20}),
        ('flow_window', 'vals', '资金流', {'k1': 'qz:60051', 'k2': 'fwd:20261001,' + date}),
    ):
        rows = query(cmd, table, **params)
        if name in {'daily_window', 'flow_window'}:
            # Range consumers group by code/date, so compare the records independently of index order.
            rows = sorted(rows, key=lambda row: (row['code'], row['date']))
        yield name, rows
    for frequency in ('1d', '1w', '1M', '1m', '5m', '15m', '30m', '60m'):
        yield frequency, read(sdk, '/kline', code='600519', frequency=frequency, start='20261001', end=date)
    yield 'industry_week', read(sdk, '/kline', code='801790.SL', frequency='1w', start='20261001', end=date)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--rd', default='http://stockdb-local:7899')
    parser.add_argument('--sdk', default='http://stockdb-local:7900')
    parser.add_argument('--baseline')
    args = parser.parse_args()
    expected = json.loads(args.baseline) if args.baseline else {}
    records = {}
    begun = monotonic()
    for name, data in samples(args.rd, args.sdk):
        if not data:
            raise RuntimeError(f'Empty verification sample {name}')
        records[name] = [len(data), digest(data)]
        print(name, records[name][0], 'match' if expected.get(name) == records[name] else '', flush=True)
    print(json.dumps(records, separators=(',', ':')), flush=True)
    print(f'{monotonic()-begun:.1f}s', flush=True)
    if expected and records != expected:
        raise SystemExit('Different results: ' + ', '.join(k for k in records if expected.get(k) != records[k]))


if __name__ == '__main__':
    main()

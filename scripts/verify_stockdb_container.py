"""Capture real-data SDK samples or compare a migrated service to a baseline."""
import argparse
import json
import math
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CASES = [(code, frequency) for code in ('600519', '510300')
         for frequency in ('1d', '15m', '1w', '1M')]
CASES += [('801080.SL', frequency) for frequency in ('1d', '1w', '1M')]


def same(actual, expected):
    if isinstance(expected, dict):
        return isinstance(actual, dict) and actual.keys() == expected.keys() and all(same(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(same(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, (float, int)) and not isinstance(expected, bool):
        return isinstance(actual, (float, int)) and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-8)
    return actual == expected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:7900')
    parser.add_argument('--output', required=True)
    parser.add_argument('--compare')
    args = parser.parse_args()
    baseline = json.loads(Path(args.compare).read_text(encoding='utf-8')) if args.compare else None
    with urlopen(Request(args.base_url + '/refresh', method='POST'), timeout=180) as response:
        response.read()
    report = {}
    for code, frequency in CASES:
        key = f'{code}/{frequency}'
        first, last = ('20261102', '20261105') if frequency == '15m' else ('20240101', '20240331')
        query = urlencode(dict(code=code, frequency=frequency, start=first, end=last))
        url = args.base_url + '/kline?' + query
        started = time.monotonic()
        with urlopen(url, timeout=180) as response:
            rows = json.load(response)
        elapsed = time.monotonic() - started
        assert isinstance(rows, list) and rows, (key, rows)
        dates = [row['date'] for row in rows]
        assert dates == sorted(set(dates)), key
        for row in rows:
            assert all(math.isfinite(row[field]) for field in ('open', 'high', 'low', 'close')), key
        if baseline:
            assert same(rows, baseline[key]['rows']), f'Data mismatch: {key}'
        cached_started = time.monotonic()
        with urlopen(url, timeout=180) as response:
            assert same(json.load(response), rows), f'Cache mismatch: {key}'
        report[key] = dict(rows=rows, seconds=round(elapsed, 3), cached_seconds=round(time.monotonic()-cached_started, 3))
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
        print(f'{key}: {len(rows)} rows, cold={elapsed:.3f}s, cached={report[key]["cached_seconds"]}s', flush=True)
    print('All real-data samples passed' + ('; baseline matched' if baseline else ''), flush=True)


if __name__ == '__main__':
    main()

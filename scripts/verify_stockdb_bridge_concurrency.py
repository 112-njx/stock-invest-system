"""Verify cache/readiness responsiveness and request coalescing against real SDK work."""
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:7900')
    args = parser.parse_args()

    def request(path, method='GET'):
        try:
            response = urlopen(Request(args.base_url + path, method=method), timeout=180)
        except HTTPError as exc:
            response = exc
        with response:
            return response.code, json.load(response)

    def metrics():
        status, data = request('/metrics')
        assert status == 200, data
        return data

    assert request('/refresh', 'POST')[0] == 200
    assert request('/ready') == (200, {'status': 'ready'})
    fast_path = '/kline?code=600519&frequency=1d&start=20240102&end=20240105'
    expected = request(fast_path)
    assert expected[0] == 200 and expected[1]
    before = metrics()['counts']
    slow_path = '/kline?code=801080.SL&frequency=1d&start=20000101&end=20240331'
    with ThreadPoolExecutor(5) as pool:
        first = pool.submit(request, slow_path)
        deadline = time.monotonic() + 10
        while metrics()['inflight'] != 1:
            assert not first.done(), 'Long query finished before concurrent requests were tested'
            assert time.monotonic() < deadline, 'SDK did not start'
            time.sleep(.01)
        followers = [pool.submit(request, slow_path) for _ in range(2)]
        while metrics()['counts']['shared_requests'] - before['shared_requests'] < 2:
            assert time.monotonic() < deadline, 'Duplicate requests were not coalesced'
            time.sleep(.01)
        begun = time.monotonic()
        assert pool.submit(request, fast_path).result(timeout=1) == expected
        cached_seconds = time.monotonic() - begun
        begun = time.monotonic()
        assert pool.submit(request, '/ready').result(timeout=1) == (200, {'status': 'ready'})
        readiness_seconds = time.monotonic() - begun
        assert not first.done(), 'Did not test cache access while SDK was still running'
        result = first.result(timeout=180)
        assert all(f.result(timeout=180) == result for f in followers), 'Shared results differ'
    after = metrics()['counts']
    calls = after['sdk_calls'] - before['sdk_calls']
    assert calls == 1, calls
    print(json.dumps({'sdk_calls_for_3_requests': calls,
                      'shared_requests': after['shared_requests'] - before['shared_requests'],
                      'cached_seconds': round(cached_seconds, 4),
                      'readiness_seconds': round(readiness_seconds, 4),
                      'long_query_status': result[0],
                      'long_query_rows_or_error': len(result[1]) if result[0] == 200 else result[1]},
                     ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()

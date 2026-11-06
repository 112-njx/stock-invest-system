"""Local HTTP transport for the installed Free-StockDB official SDK.

Run with the Python version matching stockdb.pyd. No market calculations live here.
"""
import argparse
import json
import re
import sys
import multiprocessing
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs, urlparse


def _industry_sdk(client, code, frequency, end):
    board = client.bk.get(code, 1)
    if not board or board.get('category') != '申万一级':
        raise ValueError('unknown sw1 board')
    last = int(end[:8]) if end != 'N' else int(date.today().strftime('%Y%m%d'))
    history = []
    for year in range(2000, last // 10000 + 1):
        # An overlap supplies the SDK's preceding effective close and preserves
        # its native equal-weight returns. No daily-to-week/month aggregation.
        first = f'{year-1}1001' if history else f'{year}0101'
        boundary = date(year, 12, 31)
        if frequency == '1w':
            boundary += timedelta(days=6-boundary.weekday())
        through = str(min(int(boundary.strftime('%Y%m%d')), last))
        rows = client.zb.get('zhishu', board['symbols'], start=first, end=through,
                             frequency=frequency, fq='qfq', method=1, base=1000)
        if not rows:
            continue
        scale = 1.0
        if history:
            overlap = next((row for row in rows if row['date'] == history[-1]['date']), None)
            if overlap is None or not overlap['close']:
                raise ValueError('SDK index overlap unavailable; cannot preserve index base')
            scale = history[-1]['close'] / overlap['close']
        cutoff = history[-1]['date'] if history else 0
        for row in rows:
            if row['date'] > cutoff:
                row = dict(row)
                for field in ('open', 'high', 'low', 'close'):
                    row[field] *= scale
                history.append(row)
    return history


def _sdk_worker(connection, sdk_dir, code, frequency, start, end):
    try:
        sys.path.insert(0, sdk_dir)
        import stock_sdk
        if code.endswith('.SL'):
            rows = _industry_sdk(stock_sdk, code, frequency, end)
            rows = [row for row in rows if str(row['date']) >= start]
        else:
            rows = stock_sdk.StockDBClient().get_data(code, start=start, end=end, frequency=frequency, fq='qfq')
        connection.send((True, rows))
    except Exception as exc:
        connection.send((False, str(exc)))
    finally:
        connection.close()


def sdk_query(sdk_dir, code, frequency, start, end):
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_sdk_worker, args=(sender, sdk_dir, code, frequency, start, end))
    process.start()
    sender.close()
    try:
        if not receiver.poll(170):
            raise TimeoutError('Free-StockDB SDK timed out')
        success, rows = receiver.recv()
        if not success:
            raise ValueError(rows)
        return rows
    finally:
        receiver.close()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk-dir', default=r'D:\Free_stockdb\stockdb\pybao')
    parser.add_argument('--port', type=int, default=7900)
    args = parser.parse_args()
    lock = Lock()
    cache = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != '/refresh':
                self.send_error(404)
                return
            with lock:
                cache.clear()
            encoded = b'{"status":"cleared"}'
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            try:
                url = urlparse(self.path)
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                if url.path == '/health':
                    result = {'status': 'ok'}
                elif url.path == '/kline':
                    code = query['code']
                    frequency = query.get('frequency', '1d')
                    if not re.fullmatch(r'\d{6}(?:\.SL)?', code) or frequency not in {'1d', '15m', '1w', '1M'}:
                        raise ValueError('invalid code/frequency')
                    start, end = query.get('start', '20000101'), query.get('end', 'N')
                    if not re.fullmatch(r'\d{8}(?:\d{6})?', start) or not re.fullmatch(r'N|\d{8}(?:\d{6})?', end):
                        raise ValueError('invalid date')
                    # SDK native state is process-global; serialize access and bound cached results.
                    with lock:
                        key = (code, frequency, start, end)
                        cached = cache.get(key)
                        if cached and monotonic() - cached[0] < 300:
                            result = cached[1]
                        else:
                            result = sdk_query(args.sdk_dir, code, frequency, start, end)
                            if len(cache) >= 32:
                                cache.pop(next(iter(cache)))
                            cache[key] = (monotonic(), result)
                else:
                    self.send_error(404)
                    return
                encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')
                self.send_response(200)
            except Exception as exc:
                encoded = json.dumps({'error': str(exc)}, ensure_ascii=False).encode('utf-8')
                self.send_response(503)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    ThreadingHTTPServer(('0.0.0.0', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()

"""Local HTTP transport for the installed Free-StockDB official SDK.

Run with the Python version matching stockdb.pyd. No market calculations live here.
"""
import argparse
import json
import logging
from concurrent.futures import Future
from collections import Counter
import re
import sys
import multiprocessing
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from time import monotonic, time
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
    timings = {}
    phase = 'sdk_init_ms'
    begun = monotonic()
    try:
        sys.path.insert(0, sdk_dir)
        import stock_sdk
        client = None if code.endswith('.SL') else stock_sdk.StockDBClient()
        timings['sdk_init_ms'] = (monotonic() - begun) * 1000
        phase = 'sdk_compute_ms'
        begun = monotonic()
        if code.endswith('.SL'):
            rows = _industry_sdk(stock_sdk, code, frequency, end)
            rows = [row for row in rows if str(row['date']) >= start]
        else:
            rows = client.get_data(code, start=start, end=end, frequency=frequency, fq='qfq')
        timings['sdk_compute_ms'] = (monotonic() - begun) * 1000
        connection.send((True, rows, timings))
    except Exception as exc:
        timings[phase] = (monotonic() - begun) * 1000
        connection.send((False, str(exc), timings))
    finally:
        connection.close()


class SDKQueryError(ValueError):
    def __init__(self, message, timings):
        super().__init__(message)
        self.timings = timings


def sdk_query(sdk_dir, code, frequency, start, end):
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_sdk_worker, args=(sender, sdk_dir, code, frequency, start, end))
    process.start()
    sender.close()
    try:
        if not receiver.poll(170):
            raise TimeoutError('Free-StockDB SDK timed out')
        success, rows, timings = receiver.recv()
        if not success:
            raise SDKQueryError(rows, timings)
        return rows, timings
    finally:
        receiver.close()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join()


class QueryService:
    """Short cache lock, independent native execution lock, one Future per key/version."""

    def __init__(self, query, ttl=300, capacity=32):
        self.query = query
        self.ttl, self.capacity = ttl, capacity
        self.state_lock, self.sdk_lock = Lock(), Lock()
        self.cache, self.inflight = {}, {}
        self.generation = 0
        self.counts = Counter(dict.fromkeys(('cache_hits', 'cache_misses', 'shared_requests',
                                           'sdk_calls', 'sdk_errors', 'sdk_timeouts',
                                           'requests', 'request_errors', 'refreshes'), 0))
        self.durations = {}
        self.last_success = None

    def refresh(self):
        # Existing readers may finish, but cannot republish the previous generation.
        with self.state_lock:
            self.generation += 1
            self.cache.clear()
            self.counts['refreshes'] += 1

    def get(self, key, trace):
        with self.state_lock:
            cached = self.cache.get(key)
            if cached and monotonic() - cached[0] < self.ttl:
                self.counts['cache_hits'] += 1
                trace['source'] = 'cache'
                return cached[1]
            token = (self.generation, key)
            future = self.inflight.get(token)
            owner = future is None
            if owner:
                future = Future()
                self.inflight[token] = future
                self.counts['cache_misses'] += 1
            else:
                self.counts['shared_requests'] += 1
        if not owner:
            trace['source'] = 'shared'
            begun = monotonic()
            try:
                return future.result()
            finally:
                trace['shared_wait_ms'] = (monotonic() - begun) * 1000
        trace['source'] = 'sdk'
        try:
            begun = monotonic()
            with self.sdk_lock:
                trace['queue_ms'] = (monotonic() - begun) * 1000
                with self.state_lock:
                    self.counts['sdk_calls'] += 1
                begun = monotonic()
                try:
                    rows, timings = self.query(*key)
                    trace.update(timings)
                except SDKQueryError as exc:
                    trace.update(exc.timings)
                    raise
                finally:
                    # Includes spawn, IPC, child cleanup and any lazy SDK initialization.
                    trace['sdk_total_ms'] = (monotonic() - begun) * 1000
            begun = monotonic()
            encoded = json.dumps(rows, ensure_ascii=False, allow_nan=False).encode('utf-8')
            trace['serialize_ms'] = (monotonic() - begun) * 1000
            trace['rows'] = len(rows)
            with self.state_lock:
                if token[0] == self.generation:
                    if len(self.cache) >= self.capacity:
                        self.cache.pop(next(iter(self.cache)))
                    self.cache[key] = (monotonic(), encoded)
                self.last_success = time()
            future.set_result(encoded)
            return encoded
        except Exception as exc:
            with self.state_lock:
                self.counts['sdk_errors'] += 1
                if isinstance(exc, TimeoutError):
                    self.counts['sdk_timeouts'] += 1
            future.set_exception(exc)
            raise
        finally:
            with self.state_lock:
                self.inflight.pop(token, None)

    def observe(self, trace, failed):
        with self.state_lock:
            self.counts['requests'] += 1
            self.counts['request_errors'] += int(failed)
            for name, value in trace.items():
                if name.endswith('_ms'):
                    entry = self.durations.setdefault(name, {'count': 0, 'sum_ms': 0, 'max_ms': 0})
                    entry['count'] += 1
                    entry['sum_ms'] += value
                    entry['max_ms'] = max(entry['max_ms'], value)

    def metrics(self):
        with self.state_lock:
            now = monotonic()
            lookups = sum(self.counts[name] for name in ('cache_hits', 'cache_misses', 'shared_requests'))
            snapshot = {'counts': dict(self.counts),
                        'cache_hit_ratio': self.counts['cache_hits'] / lookups if lookups else 0,
                        'cache_entries': sum(now-t < self.ttl for t, _ in self.cache.values()),
                        'inflight': len(self.inflight), 'generation': self.generation,
                        'last_success_unix': self.last_success,
                        'durations': {k: dict(v) for k, v in self.durations.items()}}
        # Filesystem reads must not hold the cache lock. Docker uses cgroup v2;
        # unsupported hosts report null, rather than an invented zero measurement.
        snapshot['memory'] = {}
        for name, filename in (('current_bytes', 'memory.current'), ('peak_bytes', 'memory.peak'),
                               ('limit_bytes', 'memory.max')):
            try:
                snapshot['memory'][name] = int((Path('/sys/fs/cgroup') / filename).read_text())
            except (OSError, ValueError):
                snapshot['memory'][name] = None
        return snapshot


def make_server(sdk_dir, host='0.0.0.0', port=7900, service=None):
    service = service or QueryService(lambda *key: sdk_query(sdk_dir, *key))
    logger = logging.getLogger('stockdb.bridge')

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != '/refresh':
                self.send_error(404)
                return
            service.refresh()
            self.respond(b'{"status":"cleared"}', 200)

        def respond(self, encoded, status):
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            begun = monotonic()
            trace = {}
            status = 200
            measured = False
            try:
                url = urlparse(self.path)
                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                if url.path == '/health':
                    encoded = b'{"status":"ok"}'
                elif url.path == '/metrics':
                    encoded = json.dumps(service.metrics()).encode('utf-8')
                elif url.path in {'/kline', '/ready'}:
                    measured = True
                    if url.path == '/ready':
                        code, frequency, start, end = '600519', '1d', '20240102', '20240105'
                    else:
                        code = query['code']
                        frequency = query.get('frequency', '1d')
                        start, end = query.get('start', '20000101'), query.get('end', 'N')
                    if not re.fullmatch(r'\d{6}(?:\.SL)?', code) or frequency not in {'1d', '15m', '1w', '1M'}:
                        raise ValueError('invalid code/frequency')
                    if not re.fullmatch(r'\d{8}(?:\d{6})?', start) or not re.fullmatch(r'N|\d{8}(?:\d{6})?', end):
                        raise ValueError('invalid date')
                    trace.update(code=code, frequency=frequency, start=start, end=end, path=url.path)
                    encoded = service.get((code, frequency, start, end), trace)
                    if url.path == '/ready':
                        rows = json.loads(encoded)
                        if not isinstance(rows, list) or not rows or not all('close' in row for row in rows):
                            raise ValueError('SDK data probe returned no valid rows')
                        encoded = b'{"status":"ready"}'
                else:
                    self.send_error(404)
                    return
            except Exception as exc:
                status = 503
                trace['error'] = str(exc)
                encoded = json.dumps({'error': str(exc)}, ensure_ascii=False).encode('utf-8')
            finally:
                if measured:
                    trace['total_ms'] = (monotonic() - begun) * 1000
                    trace['status'] = status
                    service.observe(trace, status != 200)
                    logger.info(json.dumps(trace, ensure_ascii=False))
            try:
                self.respond(encoded, status)
            except (BrokenPipeError, ConnectionResetError):
                logger.info('client disconnected before response was delivered')

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk-dir', default=r'D:\Free_stockdb\stockdb\pybao')
    parser.add_argument('--port', type=int, default=7900)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    make_server(args.sdk_dir, port=args.port).serve_forever()


if __name__ == '__main__':
    main()

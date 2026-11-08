"""Local HTTP transport for the installed Free-StockDB official SDK.

Run with the Python version matching stockdb.pyd. No market calculations live here.
"""
import argparse
import json
import logging
import os
import sqlite3
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


try:
    from stockdb_files import FullResultCache, data_version, ensure_available
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'stock_backend'))
    from app.services.stockdb_files import FullResultCache, data_version, ensure_available


class IndustryQuery:
    def __init__(self, sdk_dir, control, cache):
        self.sdk_dir, self.control, self.cache = sdk_dir, control, cache

    def lookup(self, code, frequency, start, end):
        if not code.endswith('.SL'):
            return None
        version = data_version(self.control)
        try:
            rows = self.cache.get(code + '@' + end, frequency, version)
        except (OSError, ValueError, sqlite3.DatabaseError):
            logging.getLogger('stockdb.bridge').exception('persistent cache read failed; using SDK')
            return None
        if rows is None:
            return None
        return [row for row in rows if str(row['date']) >= start], {'persistent_hit': 1}

    def __call__(self, code, frequency, start, end):
        if not code.endswith('.SL'):
            return sdk_query(self.sdk_dir, code, frequency, start, end)
        cached = self.lookup(code, frequency, start, end)
        if cached is not None:
            return cached
        version = data_version(self.control)
        # End is part of the snapshot identity: partial weeks/months must not
        # be answered by truncating a later period result.
        rows, timings = sdk_query(self.sdk_dir, code, frequency, '20000101', end)
        if data_version(self.control) != version:
            raise RuntimeError('数据版本已切换，请重新查询')
        try:
            self.cache.put(code + '@' + end, frequency, version, rows)
        except (OSError, sqlite3.DatabaseError):
            logging.getLogger('stockdb.bridge').exception('persistent cache write failed; serving SDK result')
        return [row for row in rows if str(row['date']) >= start], {**timings, 'persistent_hit': 0}


class QueryService:
    """Short cache lock, independent native execution lock, one Future per key/version."""

    def __init__(self, query, ttl=300, capacity=32, version_provider=None):
        self.query = query
        self.version_provider = version_provider
        self.memory_limit = 16 * 1024 * 1024
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

    def get(self, key, trace, probe=False):
        version = self.version_provider(probe) if self.version_provider else None
        cache_key = (version, key)
        with self.state_lock:
            cached = self.cache.get(cache_key)
            if cached and monotonic() - cached[0] < self.ttl:
                self.counts['cache_hits'] += 1
                trace['source'] = 'cache'
                return cached[1]
            token = (self.generation, version, key)
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
            cached_disk = self.query.lookup(*key) if hasattr(self.query, 'lookup') else None
            if cached_disk is not None:
                rows, timings = cached_disk
                trace.update(timings)
                with self.state_lock:
                    self.counts['disk_hits'] += 1
            else:
                with self.sdk_lock:
                    trace['queue_ms'] = (monotonic() - begun) * 1000
                    begun = monotonic()
                    try:
                        rows, timings = self.query(*key)
                        trace.update(timings)
                    except SDKQueryError as exc:
                        trace.update(exc.timings)
                        raise
                    finally:
                        trace['sdk_total_ms'] = (monotonic() - begun) * 1000
                        with self.state_lock:
                            self.counts['disk_hits' if trace.get('persistent_hit') else 'sdk_calls'] += 1
            if trace.get('persistent_hit'):
                trace['source'] = 'disk'
            begun = monotonic()
            encoded = json.dumps(rows, ensure_ascii=False, allow_nan=False).encode('utf-8')
            trace['serialize_ms'] = (monotonic() - begun) * 1000
            trace['rows'] = len(rows)
            if self.version_provider and self.version_provider(probe) != version:
                raise RuntimeError('数据版本已切换，请重新查询')
            with self.state_lock:
                if token[0] == self.generation and len(encoded) <= self.memory_limit:
                    if len(self.cache) >= self.capacity:
                        self.cache.pop(next(iter(self.cache)))
                    self.cache[cache_key] = (monotonic(), encoded)
                    while sum(len(value[1]) for value in self.cache.values()) > self.memory_limit:
                        self.cache.pop(next(iter(self.cache)))
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
                        'memory_cache_bytes': sum(len(value[1]) for value in self.cache.values()),
                        'memory_cache_limit_bytes': self.memory_limit,
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


def indicator_registry():
    import importlib.util
    path = Path(__file__).with_name('indicator_registry.py')
    if not path.exists():
        path = Path(__file__).resolve().parents[1] / 'stock_backend/app/services/indicator_registry.py'
    spec = importlib.util.spec_from_file_location('bridge_indicator_registry', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _composite_data_worker(connection, sdk_dir, jobs, frequency, start, end):
    """Fetch and aggregate each member using the official SDK, in its own process."""
    try:
        sys.path.insert(0, sdk_dir)
        from zhibiao import _load_rows
        for index, code in jobs:
            if frequency in {'1m', '5m', '15m', '30m', '60m'}:
                # SDK aggregation is per trading day. Day-aligned windows keep
                # every bar intact while avoiding millions of raw minute dicts
                # in memory at once. Qfq still uses the SDK client's same full
                # factor snapshot in every window.
                from datetime import datetime
                first = datetime.strptime(start[:8], '%Y%m%d').date()
                last = datetime.strptime(end[:8], '%Y%m%d').date()
                arrays = [[] for _ in range(10)]
                while first <= last:
                    through = min(first + timedelta(days=89), last)
                    low = start if first.strftime('%Y%m%d') == start[:8] else first.strftime('%Y%m%d')
                    high = end if through == last else through.strftime('%Y%m%d')
                    part = _load_rows([code], frequency, low, high, 'qfq')
                    for column, values in zip(arrays, part, strict=True):
                        column.extend(values)
                    first = through + timedelta(days=1)
            else:
                arrays = _load_rows([code], frequency, start, end, 'qfq')
            connection.send((True, index, arrays))
    except (BrokenPipeError, EOFError):
        pass
    except Exception as exc:
        try:
            connection.send((False, None, str(exc)))
        except (BrokenPipeError, EOFError):
            pass
    finally:
        connection.close()


def load_composite_arrays(sdk_dir, codes, frequency, start, end, timeout=40, max_workers=4, progress=None, use_cache=True):
    """Bound memory and Python aggregation time without replacing SDK formulas.

    The SDK batch loader materializes all one-minute records before aggregating
    them. Partitioning members across four processes keeps that working set
    bounded and preserves the original member order and native per-stock bars.
    """
    from multiprocessing.connection import wait
    processes, receivers, results = [], [], {}
    deadline = monotonic() + timeout
    control = os.environ.get('STOCKDB_CONTROL_DIR')
    version = None
    cache = None
    fields = ('date', 'open', 'high', 'low', 'close', 'volume', 'amount', 'float_mv', 'total_mv')
    if control:
        ensure_available(control)
        version = data_version(control)
    cache_dir = os.environ.get('STOCKDB_CACHE_DIR')
    if use_cache and version and cache_dir:
        try:
            cache = FullResultCache(Path(cache_dir) / 'composite-inputs', max_bytes=64 * 1024 * 1024)
        except (OSError, sqlite3.DatabaseError):
            logging.getLogger('stockdb.bridge').warning('composite input cache unavailable; using SDK')
    sdk_files = [Path(sdk_dir) / 'zhibiao.py', *sorted(Path(sdk_dir).glob('zb_core*'))]
    sdk_version = [(f.name, f.stat().st_size, f.stat().st_mtime_ns) for f in sdk_files if f.exists()]
    def cache_key(code):
        return 'sdk-input-v1:' + code + '@' + json.dumps([frequency, start, end, sdk_version], separators=(',', ':'))
    if cache:
        for index, code in enumerate(codes):
            try:
                saved = cache.get(cache_key(code), frequency, version)
                if saved:
                    results[index] = [[0] * len(saved)] + [[row[f] for row in saved] for f in fields]
            except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError):
                logging.getLogger('stockdb.bridge').warning('composite input cache read failed; using SDK')
    missing = [(i, code) for i, code in enumerate(codes) if i not in results]
    workers = min(4, max_workers, len(missing))
    context = multiprocessing.get_context('spawn')
    try:
        for worker in range(workers):
            receiver, sender = context.Pipe(duplex=False)
            jobs = missing[worker::workers]
            process = context.Process(target=_composite_data_worker,
                args=(sender, sdk_dir, jobs, frequency, start, end))
            process.start()
            sender.close()
            processes.append(process)
            receivers.append(receiver)
        live = list(receivers)
        while len(results) < len(codes):
            remaining = deadline - monotonic()
            ready = wait(live, timeout=max(0, remaining)) if live and remaining > 0 else []
            if not ready:
                raise TimeoutError('合成指数本地数据读取超时')
            for receiver in ready:
                try:
                    success, index, arrays = receiver.recv()
                except EOFError:
                    live.remove(receiver)
                    continue
                if not success:
                    raise ValueError(arrays)
                results[index] = arrays
                if cache and arrays[0]:
                    try:
                        saved = [dict(zip(fields, values, strict=True)) for values in zip(*arrays[1:], strict=True)]
                        cache.put(cache_key(codes[index]), frequency, version, saved)
                    except (OSError, ValueError, sqlite3.DatabaseError):
                        logging.getLogger('stockdb.bridge').warning('composite input cache write failed; using SDK result')
                if progress is not None:
                    progress(index, len(arrays[0]))
        combined = [[] for _ in range(10)]
        for index in range(len(codes)):
            arrays = results[index]
            combined[0].extend([index] * len(arrays[0]))
            for field in range(1, 10):
                combined[field].extend(arrays[field])
        if control:
            ensure_available(control)
            if data_version(control) != version:
                raise RuntimeError('数据版本已切换，请重新查询')
        return tuple(combined)
    finally:
        for receiver in receivers:
            receiver.close()
        for process in processes:
            process.join(.1)
            if process.is_alive():
                process.terminate()
                process.join(.5)


def calculate_composite_rows(rows, chosen, period, loader=None, sdk_dir=None):
    """Use native ZHISHU, including constant user weights as its weight input.

    No index returns are calculated here. Dates and result values are native;
    only the JSON time labels are aligned to the current chart's UTC labels.
    """
    from datetime import datetime, UTC
    import math
    from zoneinfo import ZoneInfo
    from zhibiao import ZHISHU, _load_rows
    if period not in ('1d', '1w', '1mon', '1m', '5m', '15m', '30m', '60m'):
        raise ValueError('invalid composite period')
    chosen = indicator_registry().validate_composite(chosen)
    members = [m for m in chosen['members'] if chosen['weighting'] == 'equal' or m['weight'] > 0]
    codes = [m['code'] for m in members]
    end = max(datetime.fromisoformat(r['ts']).replace(tzinfo=UTC) if datetime.fromisoformat(r['ts']).tzinfo is None
              else datetime.fromisoformat(r['ts']).astimezone(UTC) for r in rows)
    end_stamp = end.astimezone(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d%H%M%S') if period in {'1m', '5m', '15m', '30m', '60m'} else end.strftime('%Y%m%d')
    if chosen['start'].replace('-', '') > end_stamp[:8]:
        return [{**row, 'zhishu_close': None, 'zhishu_count': None} for row in rows]
    control = os.environ.get('STOCKDB_CONTROL_DIR')
    version = None
    if control:
        ensure_available(control)
        version = data_version(control)
    frequency = '1M' if period == '1mon' else period
    if loader is None and sdk_dir and len(codes) > 1:
        arrays = list(load_composite_arrays(sdk_dir, codes, frequency, chosen['start'].replace('-', ''), end_stamp))
    else:
        arrays = list((loader or _load_rows)(codes, frequency, chosen['start'].replace('-', ''), end_stamp, 'qfq'))
    present = set(arrays[0])
    if any(i not in present for i in range(len(codes))):
        raise ValueError('部分所选股票在起算日期之后没有本地历史数据')
    if chosen['weighting'] == 'custom':
        # method=2 consumes the supplied weight vector. Constant per-member
        # weights implement a fixed-weight return index inside zb_core.
        arrays[8] = [float(members[i]['weight']) for i in arrays[0]]
    raw = ZHISHU(*arrays, method=1 if chosen['weighting'] == 'equal' else 2, base=float(chosen['base']))
    if control:
        ensure_available(control)
        if data_version(control) != version:
            raise RuntimeError('数据版本已切换，请重新查询')
    by_time = {}
    for index, stamp in enumerate(raw[0]):
        stamp = str(stamp)
        time = datetime.strptime(stamp, '%Y%m%d%H%M%S' if len(stamp) == 14 else '%Y%m%d')
        time = time.replace(tzinfo=ZoneInfo('Asia/Shanghai') if len(stamp) == 14 else UTC).astimezone(UTC)
        by_time[time.timestamp()] = (raw[4][index], raw[8][index])
    output = []
    for row in rows:
        time = datetime.fromisoformat(row['ts'])
        if time.tzinfo is None:
            time = time.replace(tzinfo=UTC)
        value, count = by_time.get(time.timestamp(), (None, None))
        output.append({**row, 'zhishu_close': float(value) if value is not None and math.isfinite(value) else None,
                       'zhishu_count': count})
    return output


def calculate_indicator_rows(sdk_dir, payload):
    """Native calculations only; never fetch an independently based price series."""
    import math
    sys.path.insert(0, sdk_dir)
    from zhibiao import zb
    rows, names, params = payload['rows'], payload['names'], payload.get('params') or {}
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100000:
        raise ValueError('invalid history length')
    registry = indicator_registry()
    if not isinstance(names, list) or not names or any(n not in registry.REGISTRY for n in names):
        raise ValueError('unsupported indicator')
    if not isinstance(params, dict):
        raise ValueError('invalid parameters')
    def array(field):
        values = [float(row[field]) for row in rows]
        if not all(math.isfinite(v) for v in values):
            raise ValueError('nonfinite input')
        return values
    output = [dict(row) for row in rows]
    def append(fields, series):
        for field, values in zip(fields, series, strict=True):
            if len(values) != len(rows):
                raise ValueError('native output length mismatch')
            for row, value in zip(output, values):
                row[field] = float(value) if math.isfinite(value) else None
    for name in names:
        definition = registry.REGISTRY[name]
        chosen = registry.validate_parameters(name, params.get(name))
        if name == 'zhishu':
            output = calculate_composite_rows(output, chosen, payload.get('period'), sdk_dir=sdk_dir)
            continue
        field, cross = registry.validate_controls(name, params.get(name))
        if name == 'ma':
            close = array('close')
            periods = chosen['periods']
            append([f'ma{n}' for n in periods], [zb.MA(close, n) for n in periods])
        elif definition['native']:
            raw = getattr(zb, definition['native'])(*[array(field if f == 'close' and definition.get('input_fields') else f) for f in definition['inputs']], *chosen.values())
            fields = definition['native_outputs']
            append(fields, raw if len(fields) > 1 else [raw])
        elif name == 'volume':
            append(('volume_ma5', 'volume_ma10'), [zb.MA(array('volume'), n) for n in (5,10)])
        if cross:
            from zhibiao import BATCH_CROSS
            raw = BATCH_CROSS([name], [list(chosen.values())], [0] * len(rows), list(range(len(rows))),
                              *[array(f) for f in ('open', 'high', 'low', 'close', 'volume')], False)
            signal = raw[3][raw[2].index('cross')]
            append([name + '_cross'], [signal])
    return output


def _indicator_worker(connection, sdk_dir, payload):
    try:
        connection.send((True, calculate_indicator_rows(sdk_dir, payload)))
    except Exception as exc:
        connection.send((False, str(exc)))
    finally:
        connection.close()


def sdk_indicators(sdk_dir, payload):
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_indicator_worker, args=(sender, sdk_dir, payload))
    process.start()
    sender.close()
    try:
        if not receiver.poll(45 if 'zhishu' in payload.get('names', []) else 35):
            raise TimeoutError('SDK indicator computation timed out')
        success, result = receiver.recv()
        if not success:
            raise ValueError(result)
        return result
    finally:
        receiver.close()
        process.join(2)
        if process.is_alive():
            process.terminate()
            process.join()


def make_server(sdk_dir, host='0.0.0.0', port=7900, service=None):
    if service is None:
        control = os.environ.get('STOCKDB_CONTROL_DIR')
        if control:
            cache = FullResultCache(os.environ.get('STOCKDB_CACHE_DIR', '/var/cache/stockdb'))
            def version(probe):
                if not probe:
                    ensure_available(control)
                return data_version(control)
            service = QueryService(IndustryQuery(sdk_dir, control, cache), version_provider=version)
        else:
            service = QueryService(lambda *key: sdk_query(sdk_dir, *key))
    logger = logging.getLogger('stockdb.bridge')
    indicator_lock = Lock()
    composite_lock = Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path in ('/online/query', '/online/policy', '/online/catalog'):
                from stockdb_online import query, policy, catalog, OnlineError
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 8192:
                        raise OnlineError('Invalid request size')
                    payload = json.loads(self.rfile.read(size))
                    result = catalog() if self.path.endswith('/catalog') else query(sdk_dir, payload) if self.path.endswith('/query') else policy(payload.get('interval_seconds'))
                    self.respond(json.dumps(result, ensure_ascii=False).encode(), 200)
                except OnlineError as exc:
                    self.respond(json.dumps({'detail': str(exc), 'retry_after': exc.retry_after}, ensure_ascii=False).encode(), exc.status)
                except Exception:
                    logger.exception('Online query failed')
                    self.respond(b'{"detail":"Online query or local storage failed"}', 502)
                return
            if self.path == '/refresh':
                service.refresh()
                self.respond(b'{"status":"cleared"}', 200)
                return
            if self.path != '/indicators/calculate':
                self.send_error(404)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 32 * 1024 * 1024:
                    raise ValueError('invalid request size')
                self.connection.settimeout(10)
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict) or not isinstance(payload.get('names'), list):
                    raise ValueError('invalid indicator payload')
                # Each native job already runs in an isolated child process.
                # A long basket read must not occupy the ordinary indicator lane.
                lane = composite_lock if 'zhishu' in payload['names'] else indicator_lock
                if not lane.acquire(timeout=5):
                    self.respond(b'{"error":"indicator engine busy; retry later"}', 503)
                    return
                try:
                    result = sdk_indicators(sdk_dir, payload)
                    self.respond(json.dumps(result, allow_nan=False).encode(), 200)
                finally:
                    lane.release()
            except ValueError as exc:
                self.respond(json.dumps({'error': str(exc)}).encode(), 400)
            except Exception as exc:
                self.respond(json.dumps({'error': str(exc)}).encode(), 503)

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
                elif url.path == '/indicators/ready':
                    probe = {'rows': [dict(ts=str(i), close=float(i+1)) for i in range(12)], 'names': ['macd']}
                    if not indicator_lock.acquire(timeout=5):
                        raise TimeoutError('indicator engine busy')
                    try:
                        rows = sdk_indicators(sdk_dir, probe)
                        if len(rows) != 12 or rows[-1].get('macd_hist') is None:
                            raise ValueError('indicator engine probe failed')
                        encoded = b'{"status":"ok"}'
                    finally:
                        indicator_lock.release()
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
                    if not re.fullmatch(r'\d{6}(?:\.SL)?', code) or frequency not in {'1m', '5m', '15m', '30m', '60m', '1d', '1w', '1M'}:
                        raise ValueError('invalid code/frequency')
                    if not re.fullmatch(r'\d{8}(?:\d{6})?', start) or not re.fullmatch(r'N|\d{8}(?:\d{6})?', end):
                        raise ValueError('invalid date')
                    trace.update(code=code, frequency=frequency, start=start, end=end, path=url.path)
                    encoded = service.get((code, frequency, start, end), trace, probe=url.path == '/ready')
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

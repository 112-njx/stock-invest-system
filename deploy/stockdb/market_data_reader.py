"""Read the mounted StockDB LevelDB snapshots through the upstream LevelDB C API."""
import ctypes as C
from heapq import merge
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import groupby, islice
import json
import logging
from pathlib import Path
import re
from shutil import copyfile
from tempfile import TemporaryDirectory
from threading import BoundedSemaphore
from urllib.parse import parse_qs, urlsplit

import msgpack

logger = logging.getLogger(__name__)
MAX_BATCH_QUERY_ROWS = 50_000
MAX_BATCH_ROWS = 100_000
MAX_BATCH_BYTES = 32 * 1024 * 1024


def encode_json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def json_array(items):
    return b'[' + b','.join(items) + b']'


class BatchLimitExceeded(ValueError):
    pass


class BatchBudget:
    def __init__(self, query_count):
        self.rows_left = MAX_BATCH_ROWS
        # Reserve brackets and separators for the batch and all sub-results.
        self.bytes_left = MAX_BATCH_BYTES - 2 - 3 * query_count

    def record(self, row):
        if self.rows_left <= 0:
            raise BatchLimitExceeded('Batch result exceeds the total row limit')
        item = encode_json(row)
        self.rows_left -= 1
        self.bytes_left -= len(item) + 1
        if self.bytes_left < 0:
            raise BatchLimitExceeded('Batch response exceeds the byte limit')
        return item


def bind_library():
    lib = C.CDLL('/usr/local/lib/libleveldb.so')
    ptr, string, size = C.c_void_p, C.c_char_p, C.c_size_t
    error = C.POINTER(string)
    signatures = {
        'options_create': (ptr,), 'options_destroy': (None, ptr),
        'options_set_cache': (None, ptr, ptr),
        'options_set_paranoid_checks': (None, ptr, C.c_ubyte),
        'cache_create_lru': (ptr, size), 'cache_destroy': (None, ptr),
        'readoptions_create': (ptr,), 'readoptions_destroy': (None, ptr),
        'readoptions_set_verify_checksums': (None, ptr, C.c_ubyte),
        'open': (ptr, ptr, string, error), 'close': (None, ptr),
        'get': (ptr, ptr, ptr, string, size, C.POINTER(size), error),
        'free': (None, ptr),
        'create_iterator': (ptr, ptr, ptr), 'iter_destroy': (None, ptr),
        'iter_valid': (C.c_ubyte, ptr), 'iter_seek': (None, ptr, string, size),
        'iter_seek_to_last': (None, ptr), 'iter_next': (None, ptr), 'iter_prev': (None, ptr),
        'iter_key': (ptr, ptr, C.POINTER(size)), 'iter_value': (ptr, ptr, C.POINTER(size)),
        'iter_get_error': (None, ptr, error),
    }
    for name, (result, *args) in signatures.items():
        function = getattr(lib, 'leveldb_' + name)
        function.restype, function.argtypes = result, args
        setattr(lib, name, function)
    return lib


LIB = bind_library()


def check_error(error):
    if error.value is not None:
        message = error.value.decode(errors='replace')
        LIB.free(C.cast(error, C.c_void_p))
        raise OSError(message)


class Snapshot:
    def __init__(self, directory):
        # LevelDB requires writable recovery metadata. Keep it in scratch.
        # SST files are immutable and opened by reference, never copied.
        self.scratch = TemporaryDirectory(prefix='market-data-')
        target = Path(self.scratch.name)
        current = (directory / 'CURRENT').read_text().strip()
        if not re.fullmatch(r'MANIFEST-\d+', current):
            raise ValueError('Invalid LevelDB CURRENT')
        for path in directory.iterdir():
            if re.fullmatch(r'\d+\.(ldb|sst)', path.name):
                (target / path.name).symlink_to(path)
            elif path.name in {'CURRENT', current} or re.fullmatch(r'\d+\.log', path.name):
                copyfile(path, target / path.name)
        if (directory / 'CURRENT').read_text().strip() != current:
            raise OSError('LevelDB snapshot changed during open')
        options = LIB.options_create()
        self.cache = LIB.cache_create_lru(96 * 1024 * 1024)
        LIB.options_set_cache(options, self.cache)
        LIB.options_set_paranoid_checks(options, 1)
        error = C.c_char_p()
        try:
            self.handle = LIB.open(options, str(target).encode(), C.byref(error))
            check_error(error)
        finally:
            LIB.options_destroy(options)
        self.read_options = LIB.readoptions_create()
        LIB.readoptions_set_verify_checksums(self.read_options, 1)

    def close(self):
        LIB.close(self.handle)
        LIB.readoptions_destroy(self.read_options)
        LIB.cache_destroy(self.cache)
        self.scratch.cleanup()

    def get(self, key):
        length, error = C.c_size_t(), C.c_char_p()
        value = LIB.get(self.handle, self.read_options, key, len(key), C.byref(length), C.byref(error))
        check_error(error)
        if value:
            try:
                return C.string_at(value, length.value)
            finally:
                LIB.free(value)
        return None

    def scan(self, lower, upper, reverse=False, values=True, dates=None):
        it = LIB.create_iterator(self.handle, self.read_options)
        length, error = C.c_size_t(), C.c_char_p()

        def read(fn):
            pointer = fn(it, C.byref(length))
            return C.string_at(pointer, length.value)

        def seek(bound):
            LIB.iter_seek(it, bound, len(bound))
            if reverse:
                if LIB.iter_valid(it):
                    LIB.iter_prev(it)
                else:
                    LIB.iter_seek_to_last(it)

        try:
            seek(upper if reverse else lower)
            step = LIB.iter_prev if reverse else LIB.iter_next
            while LIB.iter_valid(it):
                key = read(LIB.iter_key)
                if not lower <= key < upper:
                    break
                if dates:
                    # Some series also have a bare table:code metadata key.
                    series = b':'.join(key.split(b':', 2)[:2])
                    start, end = bounds(series + b':', dates)
                    seek(end if reverse else start)
                else:
                    start, end = lower, upper
                while LIB.iter_valid(it):
                    key = read(LIB.iter_key)
                    if not start <= key < end:
                        break
                    yield key, read(LIB.iter_value) if values else None
                    step(it)
                if not dates:
                    break
                seek(series if reverse else series + b':\xff')
            LIB.iter_get_error(it, C.byref(error))
            check_error(error)
        finally:
            LIB.iter_destroy(it)


def bounds(prefix, selector):
    mode, sep, value = selector.partition(':')
    if not sep:
        raise ValueError('Invalid selector')
    key = value.encode()
    if mode == 'all' and not value:
        return prefix, prefix + b'\xff'
    if mode == 'key':
        return prefix + key, prefix + key + b'\0'
    if mode == 'qz':
        return prefix + key, prefix + key + b'\xff'
    if mode in {'fwd', 'bwd'}:
        low, sep, high = key.partition(b',')
        if sep and low <= high:
            return prefix + low, prefix + high + b'\xff'
    raise ValueError('Unsupported selector')


def decode(key, value):
    if not value:
        return None
    try:
        return msgpack.unpackb(value, raw=False, strict_map_key=False)
    except ValueError:
        # The legacy reader exposes an undecodable record as JSON null.
        logger.debug('Undecodable stored record %r', key)
        return None


class MarketData:
    tables = {'股票代码', '日k', '分钟k', '复权', '板块', '资金流', '退市'}

    def __init__(self, root):
        self.snapshots = [Snapshot(root / name) for name in ('data', 'data1')]

    def get(self, key):
        for db in self.snapshots:
            value = db.get(key)
            if value is not None:
                return value
        return None

    def scan(self, lower, upper, reverse=False, values=True, dates=None):
        iterators = [db.scan(lower, upper, reverse, values, dates) for db in self.snapshots]
        try:
            for _, versions in groupby(merge(*iterators, key=lambda pair: pair[0], reverse=reverse), key=lambda pair: pair[0]):
                yield next(versions)
        finally:
            for it in iterators:
                it.close()

    def query(self, cmd='get', t='', k1='', k2='', ap='', num=0, order='', *, budget=None):
        table = t.removesuffix('*')
        if table not in self.tables or cmd not in {'get', 'keys', 'vals'}:
            raise ValueError('Unsupported table or command')
        if ap and not ap.startswith('get.'):
            raise ValueError('Unsupported field projection')
        fields = ap[4:].split(',') if ap else []
        num = int(num)
        prefix = ('k' + table).encode()
        bare = not (k1 or k2) and not t.endswith('*')
        exact = k1.startswith('key:') and k2.startswith('key:')
        if bare or exact:
            key = prefix if bare else prefix + b':' + k1[4:].encode() + b':' + k2[4:].encode()
            value = self.get(key)
            if value is None:
                return b'[]' if budget else []
            if cmd == 'keys':
                row = key[1:].decode()
            else:
                row = self.project(decode(key, value), fields)
            if budget:
                item = budget.record(row)
                return item if cmd == 'get' else json_array([item])
            return row if cmd == 'get' else [row]
        descending = order == 'desc' or (not order and k2.startswith('fwd:'))
        reverse = descending ^ (num < 0)
        if k1.startswith('key:'):
            low, high = bounds(prefix + b':' + k1[4:].encode() + b':', k2 or 'all:')
            iterator = self.scan(low, high, reverse, cmd != 'keys')
        elif not num and k2.startswith(('fwd:', 'bwd:')):
            # A multi-day request reads consecutive records from each series.
            # The date index would require a random primary lookup for every bar.
            low, high = bounds(prefix + b':', k1 or 'all:')
            iterator = self.scan(low, high, reverse, cmd != 'keys', dates=k2)
        elif k2:
            iterator = self.by_date(table, k1 or 'all:', k2, reverse, cmd != 'keys')
        else:
            prefix += b':seq:' if table == '退市' else b':'
            iterator = self.scan(prefix, prefix + b'\xff', reverse, cmd != 'keys')
        rows = []
        try:
            for key, value in islice(iterator, abs(num) or None):
                if budget and len(rows) >= MAX_BATCH_QUERY_ROWS:
                    raise BatchLimitExceeded('Batch subquery exceeds the row limit')
                logical = key[1:].decode()
                if cmd == 'keys':
                    row = logical
                else:
                    row = self.project(decode(key, value), fields)
                    if cmd == 'get':
                        row = [logical, row]
                rows.append(budget.record(row) if budget else row)
        finally:
            iterator.close()
        if num < 0:
            rows.reverse()
        return json_array(rows) if budget else rows

    @staticmethod
    def project(value, fields):
        if not fields:
            return value
        items = [value.get(field) if isinstance(value, dict) else None for field in fields]
        return items[0] if len(items) == 1 else items

    def by_date(self, table, codes, dates, reverse, values):
        prefix = f'kidx:{table}:k2:'.encode()
        # The index suffix is <date> US <logical primary key>.
        date_mode, _, date_value = dates.partition(':')
        if date_mode == 'key':
            low = prefix + date_value.encode() + b'\x1f'
            high = low + b'\xff'
        else:
            low, high = bounds(prefix, dates)
        code_low, code_high = bounds(b'', codes)
        for index, _ in self.scan(low, high, reverse, False):
            _, sep, logical = index.partition(b'\x1f')
            if not sep:
                continue
            code = logical.split(b':', 2)[1]
            if not code_low <= code < code_high:
                continue
            key = b'k' + logical
            value = self.get(key) if values else None
            if not values or value is not None:
                yield key, value


def serve():
    reader = MarketData(Path('/opt/stockdb'))
    batch_slots = BoundedSemaphore(2)

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, result):
            self.send_json(status, encode_json(result))

        def send_json(self, status, body):
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            request = urlsplit(self.path)
            try:
                args = {k: v[-1] for k, v in parse_qs(request.query).items() if k != 'json'}
                if 'budget' in args:
                    raise ValueError('Invalid query parameter')
                if request.path == '/':
                    self.respond(200, reader.query(**args))
                elif request.path == '/health':
                    self.respond(200, {'status': 'ok', 'reader': 'managed-leveldb'})
                else:
                    self.respond(404, {'error': 'unknown path'})
            except (ValueError, TypeError) as exc:
                self.respond(400, {'error': str(exc)})
            except OSError as exc:
                self.respond(503, {'error': str(exc)})

        def do_POST(self):
            if self.path != '/batch':
                self.respond(404, {'error': 'unknown path'})
                return
            if not batch_slots.acquire(blocking=False):
                self.respond(503, {'error': 'Batch reader busy; retry later'})
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 1024 * 1024:
                    raise ValueError('Invalid batch size')
                self.connection.settimeout(10)
                queries = json.loads(self.rfile.read(size))
                if not isinstance(queries, list) or not 1 <= len(queries) <= 2048:
                    raise ValueError('Invalid query count')
                budget = BatchBudget(len(queries))
                # Keep only encoded, budgeted results between scans.
                body = json_array(reader.query(**q, budget=budget) for q in queries)
                self.send_json(200, body)
            except BatchLimitExceeded as exc:
                self.respond(413, {'error': str(exc)})
            except (ValueError, TypeError) as exc:
                self.respond(400, {'error': str(exc)})
            except OSError as exc:
                self.respond(503, {'error': str(exc)})
            finally:
                batch_slots.release()

        def log_message(self, *_args):
            pass

    try:
        ThreadingHTTPServer(('0.0.0.0', 7899), Handler).serve_forever()
    finally:
        for db in reader.snapshots:
            db.close()


if __name__ == '__main__':
    serve()

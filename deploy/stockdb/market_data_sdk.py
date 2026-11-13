"""Supply the pinned upstream SDK with the managed reader's local query results."""
import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = 'http://127.0.0.1:7899'


def read(request):
    try:
        with urlopen(request, timeout=150) as response:
            return json.load(response)
    except HTTPError as exc:
        raise OSError(f'Managed reader returned {exc.code}: {exc.read(512).decode(errors="replace")}') from exc


def selector(value):
    if value == '*':
        return 'all:', ''
    if value.endswith('*'):
        return 'qz:' + value[:-1], ''
    if '<' in value or '>' in value:
        descending = '<' in value
        low, high = value.split('<' if descending else '>')
        low = '' if low == 'N' else low
        high = '9' * 14 if high == 'N' else high
        return 'fwd:' + low + ',' + high, 'desc' if descending else 'asc'
    return 'key:' + value, ''


class Query:
    def __init__(self, command, table, keys):
        self.args = dict(cmd=command, t=table)
        for index, key in enumerate(keys, 1):
            expression, order = selector(key)
            self.args['k' + str(index)] = expression
            if order:
                self.args['order'] = order

    def get(self, fields):
        self.args['ap'] = 'get.' + fields
        return self

    def do(self):
        return read(ENDPOINT + '/?' + urlencode(self.args))

    def __iter__(self):
        return iter(self.do())


class Batch:
    def __init__(self):
        self.queries = []

    def mget(self, table, *keys):
        self.queries.append(Query('get', table, keys).args)

    def do(self):
        results = []
        # Industry history loads hundreds of members in one SDK pipeline.
        # Bound each transport request while preserving member order.
        for offset in range(0, len(self.queries), 64):
            queries = self.queries[offset:offset + 64]
            request = Request(ENDPOINT + '/batch', data=json.dumps(queries).encode(),
                              headers={'Content-Type': 'application/json'})
            results.extend(read(request))
        return results


class Reader:
    def get(self, table, *keys):
        return Query('get', table, keys)

    def vals(self, table, *keys):
        return Query('vals', table, keys)

    def pipe(self):
        return Batch()


def install(stock_sdk):
    reader = Reader()
    stock_sdk._raw_rd = reader
    stock_sdk._default_raw_rd = reader
    stock_sdk._default_client = None

"""Concurrency regressions for the standalone SDK bridge; no market data needed."""
import json
import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Thread
from time import monotonic
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from tempfile import TemporaryDirectory
from unittest.mock import patch
import multiprocessing

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stockdb_sdk_bridge import QueryService, make_server, load_composite_arrays

FAST = ('600519', '1d', '20240102', '20240105')
SLOW = ('801080.SL', '1d', '20240101', '20240331')
ROWS = [{'date': 20240102, 'close': 123.5}]


def wait_for(predicate):
    deadline = monotonic() + 3
    while not predicate():
        if monotonic() >= deadline:
            raise AssertionError('Concurrent operation did not reach expected state')
        Event().wait(.005)


class BridgeTests(unittest.TestCase):
    def test_composite_lane_does_not_block_normal_native_requests(self):
        entered,release=Event(),Event()
        def native(sdk_dir,payload):
            if payload['names']==['zhishu']:
                entered.set();self.assertTrue(release.wait(3))
            return [{**row,'macd_hist':0} for row in payload['rows']]
        server=make_server('',host='127.0.0.1',port=0,service=QueryService(lambda *a:(ROWS,{})))
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        def post(name):
            request=Request(base+'/indicators/calculate',data=json.dumps(dict(names=[name],rows=[dict(ts='1',close=1.)])).encode(),headers={'Content-Type':'application/json'})
            with urlopen(request,timeout=3) as response:return json.load(response)
        try:
            with patch('stockdb_sdk_bridge.sdk_indicators',side_effect=native),ThreadPoolExecutor(2) as pool:
                index=pool.submit(post,'zhishu');self.assertTrue(entered.wait(2))
                try:
                    self.assertEqual(pool.submit(post,'ma').result(timeout=.5)[0]['close'],1.)
                    with urlopen(base+'/indicators/ready',timeout=.5) as response:self.assertEqual(response.status,200)
                finally:release.set()
                self.assertEqual(index.result(timeout=3)[0]['close'],1.)
        finally:
            release.set();server.shutdown();server.server_close();thread.join(3)

    def test_composite_reader_order_failure_timeout_and_child_cleanup(self):
        # A tiny SDK-shaped module exercises real spawned workers and pipes;
        # indicator numerical contracts are covered by the actual SDK tests.
        source='''import time
def _load_rows(codes,*args):
    result=[[] for _ in range(10)]
    for i,value in enumerate(codes):
        code=int(value)
        if code==999: raise ValueError('test data unavailable')
        if code==888: time.sleep(5)
        time.sleep(.01*(4-code%4))
        result[0].extend([i,i]);result[1].extend([20250101,20250102])
        for column in result[2:]: column.extend([float(code),float(code+1)])
    return result
'''
        original={p.pid for p in multiprocessing.active_children()}
        with TemporaryDirectory() as directory, patch.dict(os.environ, {'STOCKDB_CACHE_DIR': '', 'STOCKDB_CONTROL_DIR': ''}):
            Path(directory,'zhibiao.py').write_text(source,encoding='utf-8')
            arrays=load_composite_arrays(directory,['000003','000001','000004','000002'],'15m','20250101','20250102',timeout=5)
            self.assertEqual(arrays[0],[0,0,1,1,2,2,3,3])
            self.assertEqual(arrays[2],[3.,4.,1.,2.,4.,5.,2.,3.])
            with self.assertRaisesRegex(ValueError,'test data unavailable'):
                load_composite_arrays(directory,['000001','000999'],'15m','20250101','20250102',timeout=5)
            with self.assertRaises(TimeoutError):
                load_composite_arrays(directory,['000888'],'15m','20250101','20250102',timeout=.3)
        self.assertEqual({p.pid for p in multiprocessing.active_children()},original)

    def test_composite_input_cache_is_versioned_and_never_hides_maintenance(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            control=root/'control';control.mkdir()
            state=control/'version.json'
            state.write_text(json.dumps(dict(status='ready',version='first')))
            (root/'zhibiao.py').write_text('''def _load_rows(codes,*args):
    return [[0],[20250101]]+[[float(int(codes[0]))] for _ in range(8)]
''',encoding='utf-8')
            with patch.dict(os.environ, {'STOCKDB_CONTROL_DIR':str(control),'STOCKDB_CACHE_DIR':str(root/'cache')}):
                args=(str(root),['000001','000002'],'15m','20250101','20250102')
                expected=load_composite_arrays(*args,timeout=5)
                with patch('stockdb_sdk_bridge.multiprocessing.get_context') as context:
                    self.assertEqual(load_composite_arrays(*args),expected)
                    context.return_value.Process.assert_not_called()
                state.write_text(json.dumps(dict(status='ready',version='second')))
                fetched=[]
                self.assertEqual(load_composite_arrays(*args,timeout=5,progress=lambda i,n:fetched.append(i)),expected)
                self.assertEqual(sorted(fetched),[0,1])
                # An incomplete/corrupt cached record is a miss, never a
                # fabricated input value or a failed otherwise healthy SDK job.
                import sqlite3
                db=sqlite3.connect(root/'cache/composite-inputs/industry.sqlite3')
                try:
                    with db: db.execute("UPDATE results SET payload='[{\"date\":20250101}]'")
                finally: db.close()
                fetched.clear()
                self.assertEqual(load_composite_arrays(*args,timeout=5,progress=lambda i,n:fetched.append(i)),expected)
                self.assertEqual(sorted(fetched),[0,1])
                (control/'maintenance.json').write_text('{}')
                with self.assertRaisesRegex(RuntimeError,'正在更新'):
                    load_composite_arrays(*args)

    def test_cached_request_bypasses_running_sdk_and_duplicate_is_shared(self):
        entered, release = Event(), Event()
        calls = []

        def query(*key):
            calls.append(key)
            if key == SLOW:
                entered.set()
                self.assertTrue(release.wait(3))
            return ROWS, {}

        service = QueryService(query)
        expected = service.get(FAST, {})
        with ThreadPoolExecutor(6) as pool:
            slow = pool.submit(service.get, SLOW, {})
            self.assertTrue(entered.wait(3))
            try:
                duplicates = [pool.submit(service.get, SLOW, {}) for _ in range(3)]
                wait_for(lambda: service.metrics()['counts'].get('shared_requests') == 3)
                self.assertEqual(pool.submit(service.get, FAST, {}).result(timeout=.5), expected)
            finally:
                release.set()
            for future in [slow, *duplicates]:
                self.assertEqual(future.result(timeout=3), expected)
        self.assertEqual(calls.count(SLOW), 1)

    def test_refresh_does_not_wait_or_publish_old_inflight_result(self):
        entered, release = Event(), Event()
        calls = []

        def query(*key):
            calls.append(key)
            if len(calls) == 1:
                entered.set()
                self.assertTrue(release.wait(3))
            return [{'close': len(calls)}], {}

        service = QueryService(query)
        with ThreadPoolExecutor(3) as pool:
            old = pool.submit(service.get, FAST, {})
            self.assertTrue(entered.wait(3))
            try:
                pool.submit(service.refresh).result(timeout=.5)
                new = pool.submit(service.get, FAST, {})
                wait_for(lambda: service.metrics()['inflight'] == 2)
            finally:
                release.set()
            self.assertEqual(json.loads(old.result(timeout=3)), [{'close': 1}])
            self.assertEqual(json.loads(new.result(timeout=3)), [{'close': 2}])
        self.assertEqual(json.loads(service.get(FAST, {})), [{'close': 2}])
        self.assertEqual(len(calls), 2)

    def test_failure_reaches_all_waiters_and_next_request_retries(self):
        entered, release = Event(), Event()
        calls = []

        def query(*key):
            calls.append(key)
            if len(calls) == 1:
                entered.set()
                self.assertTrue(release.wait(3))
                raise TimeoutError('test SDK timeout')
            return ROWS, {}

        service = QueryService(query)
        with ThreadPoolExecutor(4) as pool:
            owner = pool.submit(service.get, FAST, {})
            self.assertTrue(entered.wait(3))
            try:
                followers = [pool.submit(service.get, FAST, {}) for _ in range(2)]
                wait_for(lambda: service.metrics()['counts'].get('shared_requests') == 2)
            finally:
                release.set()
            for future in [owner, *followers]:
                with self.assertRaisesRegex(TimeoutError, 'test SDK timeout'):
                    future.result(timeout=3)
        self.assertEqual(service.metrics()['inflight'], 0)
        self.assertEqual(service.metrics()['counts']['sdk_timeouts'], 1)
        self.assertEqual(json.loads(service.get(FAST, {})), ROWS)
        self.assertEqual(len(calls), 2)

    def test_expiration_and_invalid_json_are_not_served_from_cache(self):
        calls = []

        def query(*key):
            calls.append(key)
            return ([{'close': float('nan')}] if len(calls) == 1 else ROWS), {}

        service = QueryService(query, ttl=0)
        with self.assertRaises(ValueError):
            service.get(FAST, {})
        self.assertEqual(service.metrics()['inflight'], 0)
        service.get(FAST, {})
        service.get(FAST, {})
        self.assertEqual(len(calls), 3)

    def test_http_readiness_liveness_and_metrics_bypass_long_query(self):
        entered, release = Event(), Event()

        def query(*key):
            if key == SLOW:
                entered.set()
                self.assertTrue(release.wait(3))
            return ROWS, {'sdk_init_ms': 1, 'sdk_compute_ms': 2}

        service = QueryService(query)
        server = make_server('', host='127.0.0.1', port=0, service=service)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'

        def get(path):
            with urlopen(base + path, timeout=2) as response:
                return json.load(response)

        try:
            self.assertEqual(get('/ready'), {'status': 'ready'})
            with ThreadPoolExecutor(2) as pool:
                slow = pool.submit(get, '/kline?code=801080.SL&start=20240101&end=20240331')
                self.assertTrue(entered.wait(3))
                try:
                    self.assertEqual(pool.submit(get, '/ready').result(timeout=.5), {'status': 'ready'})
                    self.assertEqual(get('/health'), {'status': 'ok'})
                    self.assertEqual(get('/metrics')['inflight'], 1)
                finally:
                    release.set()
                self.assertEqual(slow.result(timeout=3), ROWS)
            metrics = get('/metrics')
            self.assertEqual(metrics['counts']['cache_hits'], 1)
            self.assertIn('sdk_init_ms', metrics['durations'])
            self.assertIn('serialize_ms', metrics['durations'])
            self.assertIn('total_ms', metrics['durations'])
            with self.assertRaises(HTTPError) as error:
                get('/kline?code=invalid')
            self.assertEqual(error.exception.code, 503)
            error.exception.close()
            with urlopen(Request(base + '/refresh', method='POST')) as response:
                self.assertEqual(json.load(response), {'status': 'cleared'})
            self.assertEqual(get('/metrics')['cache_entries'], 0)
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_empty_data_is_not_ready_but_process_is_alive(self):
        service = QueryService(lambda *key: ([], {}))
        server = make_server('', host='127.0.0.1', port=0, service=service)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(HTTPError) as error:
                urlopen(f'http://127.0.0.1:{server.server_port}/ready')
            self.assertEqual(error.exception.code, 503)
            error.exception.close()
            with urlopen(f'http://127.0.0.1:{server.server_port}/health') as response:
                self.assertEqual(json.load(response), {'status': 'ok'})
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()

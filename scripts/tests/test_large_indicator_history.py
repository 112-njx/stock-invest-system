"""Large minute histories must pass both transport and native row limits."""
import json
import os
import sys
import unittest
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stockdb_sdk_bridge import make_server, calculate_indicator_rows, indicator_registry

SDK_DIR = os.environ.get('STOCKDB_TEST_SDK_DIR', r'D:\Free_stockdb\stockdb\pybao')


class LargeHistoryTests(unittest.TestCase):
    def test_transport_accepts_more_than_old_32mb_limit(self):
        row = dict(ts='2026-11-06T01:30:00+00:00', close=10., note='x' * 350)
        payload = dict(rows=[row] * 100001, names=['ma'], params={})
        body = json.dumps(payload).encode()
        self.assertGreater(len(body), 32 * 1024 * 1024)
        self.assertLess(len(body), indicator_registry().MAX_REQUEST_BYTES)
        server = make_server('', host='127.0.0.1', port=0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def calculate(sdk_dir, received):
            self.assertEqual(len(received['rows']), 100001)
            return [dict(ts=received['rows'][-1]['ts'], ma5=10)]
        try:
            with patch('stockdb_sdk_bridge.sdk_indicators', side_effect=calculate):
                request = Request(f'http://127.0.0.1:{server.server_port}/indicators/calculate',
                                  data=body, headers={'Content-Type': 'application/json'})
                with urlopen(request, timeout=30) as response:
                    self.assertEqual(json.load(response)[0]['ma5'], 10)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    @unittest.skipUnless(os.environ.get('STOCKDB_TEST_SDK_DIR'), 'native SDK test requires explicit SDK path')
    def test_native_over_100000_bars_preserves_prefix_and_dates(self):
        count = 107523
        rows = [dict(ts=str(i), open=10., high=12., low=9., close=10.+i%11*.1, volume=100)
                for i in range(count)]
        result = calculate_indicator_rows(SDK_DIR, dict(rows=rows, names=['ma', 'macd', 'kdj']))
        self.assertEqual(len(result), count)
        self.assertEqual([r['ts'] for r in result], [r['ts'] for r in rows])
        sys.path.insert(0, SDK_DIR)
        from zhibiao import zb
        close = [r['close'] for r in rows]
        self.assertEqual(result[-1]['ma5'], zb.MA(close, 5)[-1])
        self.assertEqual(result[-1]['macd_dif'], zb.MACD(close, 12, 26, 9)[0][-1])


if __name__ == '__main__':
    unittest.main()

"""Check that a busy forecast worker leaves the legacy indicator lane available."""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Thread
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stockdb_sdk_bridge import QueryService, make_server


class ForecastLaneTest(TestCase):
    def test_forecast_has_one_slot_and_does_not_block_chart(self):
        entered, release = Event(), Event()

        def calculate(_sdk, payload):
            if "forecast_features" in payload["names"]:
                entered.set()
                if not release.wait(4):
                    raise TimeoutError("test worker was not released")
            return payload["rows"]

        server = make_server("", host="127.0.0.1", port=0, service=QueryService(lambda *_: ([], {})))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def post(*names):
            request = Request(
                f"http://127.0.0.1:{server.server_port}/indicators/calculate",
                data=json.dumps({"names": names, "rows": [{"ts": "2026-11-09"}]}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urlopen(request, timeout=2) as response:
                return json.load(response)

        try:
            with patch("stockdb_sdk_bridge.sdk_indicators", side_effect=calculate), ThreadPoolExecutor(1) as pool:
                job = pool.submit(post, "forecast_features", "macd")
                try:
                    self.assertTrue(entered.wait(2))
                    self.assertEqual(post("macd"), [{"ts": "2026-11-09"}])
                    with self.assertRaises(HTTPError) as failure:
                        post("forecast_features")
                    with failure.exception as response:
                        self.assertEqual(response.code, 503)
                finally:
                    release.set()
                self.assertEqual(job.result(timeout=2), [{"ts": "2026-11-09"}])
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            thread.join(3)

"""Run in the StockDB image with PYTHONPATH=/opt."""
from datetime import date, timedelta
import os
from pathlib import Path
import sys
from unittest import TestCase, main, skipUnless

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
SDK_DIR = os.environ.get("STOCKDB_TEST_SDK_DIR", "/opt/stockdb/pybao")
FEATURE = "forecast_features"


def series(length):
    rows = []
    for i in range(length):
        close = 100 + i / 7 + i % 9
        rows.append(dict(
            ts=(date(2024, 1, 1) + timedelta(days=i)).isoformat(),
            open=close - 1, high=close + 2, low=close - 3, close=close, volume=1000 + i,
        ))
    return rows


@skipUnless(Path(SDK_DIR).is_dir(), "requires the StockDB container with the native indicator modules")
class ForecastNativeTest(TestCase):
    def test_same_request_dispatches_to_both_libraries(self):
        from stockdb_sdk_bridge import calculate_indicator_rows

        rows = series(45)
        mixed = calculate_indicator_rows(SDK_DIR, dict(rows=rows, names=["macd", FEATURE], period="1d"))
        old = calculate_indicator_rows(SDK_DIR, dict(rows=rows, names=["macd"], period="1d"))
        self.assertEqual([{k: v for k, v in row.items() if k != FEATURE} for row in mixed], old)
        self.assertIsNone(mixed[18][FEATURE]["ema20"])
        self.assertAlmostEqual(mixed[19][FEATURE]["ema20"], sum(row["close"] for row in rows[:20]) / 20)
        self.assertIsNone(mixed[12][FEATURE]["atr14"])
        tr = [5] + [max(5, abs(curr["high"] - prev["close"]), abs(curr["low"] - prev["close"]))
                    for prev, curr in zip(rows[:13], rows[1:14])]
        self.assertAlmostEqual(mixed[13][FEATURE]["atr14"], sum(tr) / 14)
        self.assertAlmostEqual(mixed[20][FEATURE]["volume_ratio20"], 1020 / 1009.5)
        self.assertTrue(any(row[FEATURE]["confirmed_pivots"] for row in mixed))

    def test_serialized_checkpoint_matches_full_result_at_every_split(self):
        from stockdb_sdk_bridge import calculate_indicator_rows

        rows = series(105)

        def compute(items, checkpoint=None):
            return calculate_indicator_rows(SDK_DIR, dict(
                rows=items, names=[FEATURE], period="1d", return_checkpoint=True, checkpoint=checkpoint,
            ))

        full = compute(rows)
        for boundary in (1, 13, 14, 19, 20, 39, 40, 80, 104):
            prefix = compute(rows[:boundary])
            suffix = compute(rows[boundary:], prefix["checkpoint"])
            self.assertEqual(prefix["rows"] + suffix["rows"], full["rows"])
            self.assertEqual(suffix["checkpoint"], full["checkpoint"])


if __name__ == "__main__":
    main()

"""Price MA contract against the installed official zb native engine."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stockdb_sdk_bridge import calculate_indicator_rows

SDK_DIR = os.environ.get('STOCKDB_TEST_SDK_DIR', r'D:\Free_stockdb\stockdb\pybao')


@unittest.skipUnless(Path(SDK_DIR).is_dir(), 'official native SDK not installed')
class PriceMATests(unittest.TestCase):
    def calculate(self, rows):
        return calculate_indicator_rows(SDK_DIR, {'rows': rows, 'names': ['ma']})

    def test_warmup_and_values_for_all_four_periods(self):
        rows = [dict(ts=str(i), close=float(i), volume=i * 100) for i in range(1, 61)]
        result = self.calculate(rows)
        self.assertEqual([r['ts'] for r in result], [r['ts'] for r in rows])
        for n in (5, 10, 20, 30):
            field = f'ma{n}'
            self.assertTrue(all(r[field] is None for r in result[:n - 1]))
            for index in range(n - 1, len(rows)):
                expected = sum(r['close'] for r in rows[index - n + 1:index + 1]) / n
                self.assertAlmostEqual(result[index][field], expected)
        self.assertNotIn('ma5', rows[0])

    def test_history_window_retains_correct_boundary_values(self):
        rows = [dict(ts=str(i), close=float((i * 7) % 19 + 20)) for i in range(90)]
        full = self.calculate(rows)
        # A displayed page needs the previous 29 bars before cropping.
        page = self.calculate(rows[31:])[29:]
        self.assertEqual(page, full[60:])

    def test_short_history_has_no_fabricated_values(self):
        result = self.calculate([dict(ts='one', close=10.0)])
        self.assertTrue(all(result[0][f'ma{n}'] is None for n in (5, 10, 20, 30)))

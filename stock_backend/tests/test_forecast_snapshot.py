from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from app.services import forecast_snapshot as forecast


def bar(day, *, source="stockdb", volume=100):
    return SimpleNamespace(
        ts=datetime(2026, 11, day, tzinfo=UTC), source=source,
        open=10, high=12, low=9, close=11, volume=volume, amount=10 * volume,
    )


class ForecastSnapshotTest(TestCase):
    def test_close_boundary_and_no_trade_rows(self):
        def history(*args, **kwargs):
            end = args[4]
            return [item for item in [bar(5), bar(6, volume=0), bar(8), bar(9)] if item.ts <= end]

        with patch.object(forecast.kline_repo, "get_bars", side_effect=history):
            cases = [(6, 59, ["2026-11-05"]), (7, 0, ["2026-11-05", "2026-11-09"])]
            for hour, minute, expected in cases:
                as_of = datetime(2026, 11, 9, hour, minute, tzinfo=UTC)
                rows, source, _, excluded = forecast._closed_history(None, 1, as_of)
                self.assertEqual([row["ts"] for row in rows], expected)
                self.assertEqual(source, "stockdb")
                self.assertEqual(excluded, 2)

    def test_revised_history_rebuilds_instead_of_resuming(self):
        stored = {}
        rows = [{"ts": "2026-11-05", "close": 10}, {"ts": "2026-11-06", "close": 11}]
        with (
            patch.object(forecast, "_read_checkpoint", side_effect=lambda key: (None, None, stored.get(key))),
            patch.object(forecast, "_write_checkpoint", side_effect=lambda redis, key, prev, val: stored.update({key: val})),
            patch.object(forecast.sdk_indicators, "calculate",
                         side_effect=lambda rows, *args, **kwargs: {"rows": rows, "checkpoint": "resume"}) as engine,
        ):
            forecast._features(rows[:1], 1, "stockdb")
            forecast._features(rows, 1, "stockdb")
            self.assertEqual(engine.call_args.args[0], rows[1:])
            self.assertEqual(engine.call_args.kwargs["checkpoint"], "resume")
            forecast._features(rows, 1, "stockdb")
            self.assertEqual(engine.call_count, 2)
            revised = [{**rows[0], "close": 9}, rows[1]]
            forecast._features(revised, 1, "stockdb")
            self.assertEqual(engine.call_args.args[0], revised)
            self.assertIsNone(engine.call_args.kwargs["checkpoint"])
            forecast._features(rows, 1, "akshare")
            self.assertIsNone(engine.call_args.kwargs["checkpoint"])

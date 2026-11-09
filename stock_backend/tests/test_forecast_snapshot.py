from datetime import UTC, datetime
from types import SimpleNamespace
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from app.data_providers.base import KlineBar
from app.data_providers.factory import DataProviderFactory
from app.data_providers.stockdb import StockDBProvider
from app.models.symbol import Symbol
from app.repositories import kline_repo
from app.services import forecast_snapshot as forecast
from app.services import market_policy
from app.services.stockdb_files import write_json
from app.utils.db import get_session


def bar(day, *, source="stockdb", volume=100, confirmed=True):
    return SimpleNamespace(
        ts=datetime(2026, 11, day, tzinfo=UTC), source=source,
        open=10, high=12, low=9, close=11, volume=volume, amount=10 * volume, close_confirmed=confirmed,
    )


class ForecastSnapshotTest(TestCase):
    def test_close_boundary_and_no_trade_rows(self):
        today = bar(9, confirmed=False)

        def history(*args, end, **kwargs):
            return [item for item in [bar(5), bar(6, volume=0), bar(8), today] if item.ts <= end]

        with patch.object(forecast.kline_repo, "latest_bars", side_effect=history):
            cases = [
                (9, 6, 59, False, ["2026-11-05"], 2),
                (9, 7, 0, False, ["2026-11-05"], 3),
                (10, 8, 0, False, ["2026-11-05"], 3),
                (9, 8, 0, True, ["2026-11-05", "2026-11-09"], 2),
            ]
            for day, hour, minute, confirmed, expected, skipped in cases:
                today.close_confirmed = confirmed
                as_of = datetime(2026, 11, day, hour, minute, tzinfo=UTC)
                rows, source, _, excluded = forecast._closed_history(None, 1, as_of)
                self.assertEqual([row["ts"] for row in rows], expected)
                self.assertEqual(source, "stockdb")
                self.assertEqual(excluded, skipped)

    def test_fetch_start_controls_confirmation(self):
        provider = SimpleNamespace(name="eastmoney")
        session = datetime(2026, 11, 9, tzinfo=UTC)
        candle = KlineBar(session, 10, 12, 9, 11, 100, 1000)
        for hour, minute, confirmed in [(6, 59, False), (7, 0, True)]:
            started = session.replace(hour=hour, minute=minute)
            DataProviderFactory._label_bars([candle], provider, "1d", started)
            self.assertEqual(candle.close_confirmed, confirmed)

    def test_stockdb_reread_needs_a_post_close_download(self):
        session = datetime(2026, 11, 9, tzinfo=UTC)
        bar = KlineBar(session, 10, 12, 9, 11, 100, 1000)
        requested = session.replace(hour=9)
        provider = StockDBProvider()
        with TemporaryDirectory() as control, patch.dict("os.environ", {"STOCKDB_CONTROL_DIR": control}):
            manifest = Path(control) / "version.json"
            for hour, confirmed in [(6, False), (7, True)]:
                write_json(manifest, {
                    "status": "ready", "updated_at": requested.timestamp(),
                    "download_started_at": session.replace(hour=hour).timestamp(),
                })
                DataProviderFactory._label_bars([bar], provider, "1d", requested)
                self.assertEqual(bar.close_confirmed, confirmed)

    def test_persisted_confirmation_and_same_source_as_preview(self):
        session = datetime(2026, 11, 9, tzinfo=UTC)
        older = session.replace(day=6)
        as_of = session.replace(hour=8)
        local = KlineBar(session, 10, 12, 9, 11, 100, 1000)
        remote = [KlineBar(day, 20, 22, 19, 21, 100, 2000, "akshare", True) for day in (older, session)]
        with (
            get_session() as db,
            patch.object(market_policy, "read", return_value={"akshare_enabled": True, "history_storage_enabled": True}),
        ):
            symbol = Symbol(code="999999", name=f"forecast-{uuid4()}", market="SSE", type="stock")
            db.add(symbol)
            db.flush()
            kline_repo.upsert_bars(db, "1d", symbol.id, remote + [local])
            self.assertEqual(kline_repo.latest_bars(db, "1d", symbol.id)[0].source, "stockdb")
            self.assertEqual(forecast._closed_history(db, symbol.id, as_of)[:2], ([], "stockdb"))
            local.close_confirmed = True
            self.assertEqual(kline_repo.upsert_bars(db, "1d", symbol.id, [local]), 1)
            local.close_confirmed = False
            local.close = 10
            self.assertEqual(kline_repo.upsert_bars(db, "1d", symbol.id, [local]), 0)
            db.expire_all()
            rows, source, _, _ = forecast._closed_history(db, symbol.id, as_of)
            self.assertEqual(source, "stockdb")
            self.assertEqual([row["close"] for row in rows], [11])
            db.rollback()

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

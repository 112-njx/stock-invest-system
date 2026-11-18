"""Regressions for local qfq conversion, fallback, and manual scheduling."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.data_providers.base import ProviderError
from app.data_providers.factory import DataProviderFactory, ProviderCircuit
from app.data_providers.stockdb import StockDBProvider
from app.worker.beat import build_beat_schedule


def test_qfq_preserves_etf_precision_and_uses_full_factor_timeline(monkeypatch):
    provider = StockDBProvider()

    def query(command, table, **params):
        if table == "复权":
            return [["复权:510300:20200101", {"cum": 1}], ["复权:510300:20251101", {"cum": 2}]]
        return [{"code": "510300", "date": 20241008, "open": 4.086, "high": 4.108,
                 "low": 4.080, "close": 4.098, "volume": 100, "amount": 410}]

    monkeypatch.setattr(provider, "query", query)
    result = provider.fetch_kline("510300", "1d", datetime(2024, 10, 8, tzinfo=UTC),
                                  datetime(2024, 10, 8, 23, tzinfo=UTC), "etf")
    assert result[0].open == 2.043
    assert result[0].close == 2.049
    assert result[0].volume == 1  # 100 shares, matching the existing AkShare lot convention.
    assert result[0].ts == datetime(2024, 10, 8, tzinfo=UTC)


def test_minute_buckets_cover_sessions_without_counting_lunch_twice():
    records = []
    for stamp in [930, 931, 945, 946, 1130, 1300, 1301, 1315, 1500]:
        records.append({"date": int(f"20261104{stamp:04d}00"), "open": 1, "high": 3,
                        "low": 1, "close": 2, "volume": 1, "amount": 2})
    bars = StockDBProvider._aggregate_minutes(records)
    assert [bar["date"] for bar in bars] == [20261104094500, 20261104100000, 20261104113000,
                                             20261104131500, 20261104150000]
    assert sum(bar["volume"] for bar in bars) == len(records)
    assert bars[3]["volume"] == 3


def test_daily_utc_session_boundary_does_not_include_the_next_local_day(monkeypatch):
    provider = StockDBProvider()

    def query(command, table, **params):
        if table == "复权":
            return []
        assert params["k2"] == "fwd:20261104,20261104"
        return [{"code": "600519", "date": day, "open": 10, "close": 10, "high": 11, "low": 9}
                for day in [20261104, 20261105]]

    monkeypatch.setattr(provider, "query", query)
    result = provider.fetch_kline("600519", "1d", datetime(2026, 11, 4, tzinfo=UTC),
                                  datetime(2026, 11, 4, 23, 59, tzinfo=UTC))
    assert len(result) == 1
    assert result[0].ts == datetime(2026, 11, 4, tzinfo=UTC)


def test_index_code_collision_never_queries_local_stock_prices(monkeypatch):
    provider = StockDBProvider()
    query = Mock()
    monkeypatch.setattr(provider, "query", query)
    assert provider.fetch_kline("000001", "1d", datetime.now(UTC), datetime.now(UTC), "index") == []
    query.assert_not_called()
    assert not hasattr(provider, "fetch_realtime")


def test_daily_chart_reads_stockdb_before_cache_and_preserves_pagination(monkeypatch):
    from app.data_providers.base import KlineBar
    from app.services import market_service

    stamps = [datetime(2026, 11, day, tzinfo=UTC) for day in (5, 6, 9, 12)]
    bars = [KlineBar(stamp, 100, 102, 99, 101, 1000, 1e6) for stamp in stamps]
    fetch = Mock(side_effect=lambda code, period, start, end, asset: [
        bar for bar in bars if start.date() <= bar.ts.date() <= end.date()
    ])
    stale_cache = Mock(return_value=[{"ts": stamps[0].isoformat()}])
    monkeypatch.setattr(StockDBProvider, "fetch_kline", fetch)
    monkeypatch.setattr(market_service, "resolve_symbol_id", lambda *args: 1)
    monkeypatch.setattr(market_service.market_cache, "get_kline_cache", stale_cache)
    db = Mock()
    db.get.return_value = SimpleNamespace(code="300308", type="stock")

    latest = market_service.get_kline(db, "300308", "1d", limit=2)
    assert [row["ts"] for row in latest] == [stamp.isoformat() for stamp in stamps[-2:]]
    ranged = market_service.get_kline(db, "300308", "1d", start=stamps[0] + timedelta(hours=1),
                                      end=stamps[-1], limit=1, offset=1)
    assert [row["ts"] for row in ranged] == [stamps[2].isoformat()]
    stale_cache.assert_not_called()

    fetch.side_effect = ProviderError("offline")
    assert market_service.get_kline(db, "300308", "1d", limit=2) == []
    stale_cache.assert_not_called()


@pytest.mark.parametrize("local", [[], ProviderError("offline")])
def test_watchlist_history_falls_back_when_local_is_empty_or_offline(local, monkeypatch):
    monkeypatch.setattr("app.services.market_policy.akshare_enabled", lambda: True)
    factory = DataProviderFactory.__new__(DataProviderFactory)
    import threading

    factory._lock = threading.Lock()
    first = SimpleNamespace(name="stockdb", can_fetch_kline=lambda *args: True,
                            fetch_kline=Mock(side_effect=local) if isinstance(local, Exception) else Mock(return_value=local))
    second = SimpleNamespace(name="eastmoney", can_fetch_kline=lambda *args: True, fetch_kline=Mock(return_value=["bar"]))
    factory._providers = [first, second]
    factory._circuits = {p.name: ProviderCircuit(3, 600) for p in factory._providers}
    assert factory.fetch_kline_all("600519", "1d", datetime.now(UTC) - timedelta(days=10), datetime.now(UTC)) == ["bar"]
    second.fetch_kline.assert_called_once()


def test_automatic_kline_incremental_schedule_removed():
    schedule = build_beat_schedule()
    assert not any(item["task"].endswith(".kline_incremental") for item in schedule.values())
    assert "realtime-poll" not in schedule
    assert list(schedule) == ["stockdb-update-daily"]
    daily = schedule["stockdb-update-daily"]
    assert daily["schedule"].hour == {16} and daily["schedule"].minute == {30}
    assert daily["schedule"].day_of_week == set(range(7))


def test_daily_update_uses_same_controller_and_submits_once(tmp_path, monkeypatch):
    from time import time
    from app.services import market_policy, stockdb_update
    from app.services.stockdb_files import read_json, write_json
    from app.worker.tasks.sync_tasks import update_stockdb_daily

    monkeypatch.setenv("STOCKDB_CONTROL_DIR", str(tmp_path))
    write_json(tmp_path / "heartbeat.json", {"kind": "linux-container", "time": time()})
    monkeypatch.setattr(market_policy, "read", lambda: {"auto_update_enabled": False})
    assert "skipped" in update_stockdb_daily()
    assert not (tmp_path / "request.json").exists()

    monkeypatch.setattr(market_policy, "read", lambda: {"auto_update_enabled": True})
    posted = update_stockdb_daily()
    request = read_json(tmp_path / "request.json")
    assert posted["status"] == "queued"
    assert request["task_id"] == posted["task_id"] and request["operation"] == "update"
    assert "skipped" in update_stockdb_daily()
    assert read_json(tmp_path / "request.json") == request


def test_retired_import_routes_are_gone(client):
    assert client.get("/api/v1/admin/local-market/sync").status_code == 404
    assert client.post("/api/v1/admin/local-market/sync").status_code == 404


def test_postgres_upsert_replaces_old_qfq_prices_and_is_idempotent():
    from uuid import uuid4
    from app.data_providers.base import KlineBar
    from app.models.symbol import Symbol
    from app.repositories import kline_repo
    from app.utils.db import get_session

    db = get_session()
    try:
        symbol = Symbol(code="999990", name=f"test_qfq_{uuid4().hex}", type="stock", market="SSE")
        db.add(symbol)
        db.flush()
        ts = datetime(2026, 11, 4, tzinfo=UTC)
        old = KlineBar(ts, 10, 12, 9, 11, 1000, 11000)
        revised = KlineBar(ts, 5, 6, 4.5, 5.5, 1000, 11000)
        assert kline_repo.upsert_bars(db, "1d", symbol.id, [old]) == 1
        assert kline_repo.upsert_bars(db, "1d", symbol.id, [revised, revised]) == 1
        assert kline_repo.upsert_bars(db, "1d", symbol.id, [revised]) == 0
        assert float(kline_repo.latest_bars(db, "1d", symbol.id)[0].close) == 5.5
    finally:
        db.rollback()
        db.close()

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
    assert "local-market-after-close" in schedule


def test_manual_sync_and_status_require_admin(client):
    assert client.post("/api/v1/admin/local-market/sync").status_code == 401
    assert client.get("/api/v1/admin/local-market/sync").status_code == 401


def test_manual_duplicate_submission_reuses_existing_task(monkeypatch):
    from app.services import local_market_sync

    db = Mock()
    db.scalar.return_value = SimpleNamespace(status="running", celery_task_id="existing")
    monkeypatch.setattr(local_market_sync, "get_session", lambda: db)
    assert local_market_sync.request_sync() == {"status": "running", "task_id": "existing"}
    db.add.assert_not_called()


def test_manual_api_accepts_admin_submission_and_returns_progress(client, monkeypatch):
    from app.api.deps import get_current_admin
    from app.main import app
    from app.services import local_market_sync

    request = Mock(return_value={"status": "queued", "task_id": "manual-job"})
    dispatch = Mock()
    monkeypatch.setattr(local_market_sync, "request_sync", request)
    monkeypatch.setattr(local_market_sync, "dispatch", dispatch)
    monkeypatch.setattr(local_market_sync, "status", lambda db: {"status": "running", "progress": 42})
    app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(is_admin=True)
    try:
        response = client.post("/api/v1/admin/local-market/sync")
        assert response.status_code == 200
        assert response.json()["data"]["task_id"] == "manual-job"
        dispatch.assert_called_once()
        assert client.get("/api/v1/admin/local-market/sync").json()["data"]["progress"] == 42
    finally:
        app.dependency_overrides.pop(get_current_admin)


@pytest.mark.parametrize('missing_period', [None, '1w', '1mon'])
def test_completed_watchlist_is_not_queued_again_when_source_date_is_old(monkeypatch, missing_period):
    from app.services import local_market_sync, watchlist_delivery
    from app.worker.celery_app import celery_app

    db = Mock()
    db.scalars.side_effect = [[7], [], []]
    db.get.side_effect = [SimpleNamespace(type="stock", code="600519", market="SSE"),
                          SimpleNamespace(status="complete", checked_to=datetime(2000, 1, 1).date())]
    db.scalar.return_value = None
    monkeypatch.setattr("app.repositories.kline_repo.latest_ts", lambda db, period, sid:
                        None if period == missing_period else datetime(2000, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(watchlist_delivery, "get_session", lambda: db)
    monkeypatch.setattr(local_market_sync, "dispatch", Mock())
    monkeypatch.setattr(celery_app.control, "inspect", lambda **kwargs: SimpleNamespace(active=lambda: {}))
    queue = Mock()
    monkeypatch.setattr(watchlist_delivery, "queue_watchlist_sync", queue)
    assert watchlist_delivery.dispatch_watchlist_sync() == {"published": 0}
    queue.assert_not_called()


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


@pytest.mark.parametrize("offline", [False, True])
@pytest.mark.parametrize("stale_period", [None, "1d", "15m"])
def test_manual_job_uses_source_date_and_refreshes_existing_history(monkeypatch, offline, stale_period):
    from uuid import uuid4
    from sqlalchemy import delete, select
    from app.data_providers.base import KlineBar
    from app.data_providers import factory
    from app.models.symbol import Symbol
    from app.models.ops import SyncTask, SyncStatus
    from app.models.kline_quality import KlineQuality
    from app.models.kline import KLINE_MODELS
    from app.repositories import kline_repo
    from app.services import local_market_sync, sync_service
    from app.utils.db import get_session

    if offline:
        monkeypatch.setattr("app.services.market_policy.akshare_enabled", lambda: True)
    scope = "test_local_" + uuid4().hex[:12]
    monkeypatch.setattr(local_market_sync, "TASK_TYPE", scope)
    db = get_session()
    target = Symbol(code="600519", name=scope, type="stock", market="SSE")
    db.add(target)
    db.flush()
    target_id = target.id
    first = datetime(2024, 1, 2, tzinfo=UTC)
    last = datetime(2025, 1, 2, tzinfo=UTC)
    initial_price = 5 if stale_period else 10
    kline_repo.upsert_bars(db, "1d", target_id, [
        KlineBar(first, initial_price, initial_price, initial_price, initial_price, 100, 1000)
    ])
    if stale_period:
        newer = last + timedelta(days=1)
        kline_repo.upsert_bars(db, stale_period, target_id, [KlineBar(newer, 6, 6, 6, 6, 200, 1200)])
    db.commit()
    before = {period: [(bar.ts, float(bar.close)) for bar in kline_repo.latest_bars(db, period, target_id)]
              for period in ("1d", "15m")}

    def session():
        connection = get_session()
        connection.scalars = Mock(return_value=[SimpleNamespace(id=target_id, name=scope, type="stock", market="SSE")])
        return connection

    def fetch(symbol, period, start, end, asset_type):
        assert start <= first
        target = datetime.now(sync_service.settings.tz).date() if offline else last.date()
        assert end.astimezone(sync_service.settings.tz).date() == target
        price = 10 if stale_period else 5
        return [KlineBar(first, price, price, price, price, 100, 1000),
                KlineBar(last, 6, 6, 6, 6, 200, 1200)]

    provider = SimpleNamespace(fetch_kline=fetch)
    monkeypatch.setattr(local_market_sync, "get_session", session)
    def source_date(self):
        if offline:
            raise ProviderError("offline")
        return last.date()

    monkeypatch.setattr(StockDBProvider, "latest_day", source_date)
    monkeypatch.setattr(StockDBProvider, "refresh_sdk", lambda self: None)
    monkeypatch.setattr(factory, "get_provider", lambda: SimpleNamespace(probe=lambda: []))
    monkeypatch.setattr(sync_service, "get_provider", lambda: provider)
    monkeypatch.setattr(sync_service, "run_catalog_sync", lambda **kwargs: {})
    write = Mock(wraps=sync_service._write_bars)
    monkeypatch.setattr(sync_service, "_write_bars", write)
    try:
        task = local_market_sync.request_sync()
        assert local_market_sync.request_sync()["task_id"] == task["task_id"]
        result = local_market_sync.run(task["task_id"])
        if stale_period:
            write.assert_not_called()  # Do not publish a rebased daily bar before validating 15m.
            assert len(result["failed"]) == 1
            assert "已阻止覆盖" in result["failed"][0]
            assert local_market_sync.status(db)["status"] == "failed"
            for period, expected in before.items():
                actual = [(bar.ts, float(bar.close)) for bar in kline_repo.latest_bars(db, period, target_id)]
                assert actual == expected
            return
        assert result["failed"] == []
        assert local_market_sync.status(db)["status"] == "success"
        bars = kline_repo.latest_bars(db, "1d", target_id)
        assert [float(bar.close) for bar in bars] == [5, 6]
        quality = db.scalar(select(KlineQuality).where(KlineQuality.symbol_id == target_id))
        assert quality.status == "complete"
        assert quality.checked_to == last.date()
    finally:
        db.rollback()
        for model in KLINE_MODELS.values():
            db.execute(delete(model).where(model.symbol_id == target_id))
        db.execute(delete(KlineQuality).where(KlineQuality.symbol_id == target_id))
        db.execute(delete(SyncTask).where((SyncTask.symbol_id == target_id) | (SyncTask.task_type == scope)))
        db.execute(delete(SyncStatus).where(SyncStatus.scope == scope))
        db.execute(delete(Symbol).where(Symbol.id == target_id))
        db.commit()
        db.close()

"""Regression coverage for cache-only AkShare history."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from app.data_providers.base import KlineBar, ProviderError
from app.models.kline import Kline1d
from app.models.symbol import Symbol
from app.repositories import kline_repo
from app.services import market_policy, source_history, indicator_service, sync_service
from app.utils.db import get_session
from app.utils.redis_client import get_redis_client


@pytest.fixture
def history(monkeypatch):
    policy = dict(akshare_enabled=True, auto_update_enabled=False, revision=900000)
    monkeypatch.setattr(market_policy, 'read', lambda: dict(policy))
    db = get_session()
    symbol = Symbol(code='601398', name='history-mode-' + uuid4().hex, type='stock', market='SSE')
    db.add(symbol); db.commit(); db.refresh(symbol)
    bars = [KlineBar(datetime(2026, 10, 1, tzinfo=UTC) + timedelta(days=i),
                     100+i, 104+i, 99+i, 102+i, 1000, 10000, source='akshare') for i in range(40)]
    provider = Mock()
    provider._active_providers.return_value = [SimpleNamespace(name='eastmoney', can_fetch_kline=lambda *args: True)]
    provider.fetch_kline_checked.return_value = (bars, True)
    provider.fetch_kline.return_value = bars
    provider.fetch_kline_all.return_value = bars
    monkeypatch.setattr(source_history, 'get_provider', lambda: provider)
    monkeypatch.setattr(sync_service, 'get_provider', lambda: provider)
    monkeypatch.setattr('app.services.local_history.read', lambda *args, **kwargs: [])
    try:
        yield db, symbol, bars, provider, policy
    finally:
        db.rollback()
        for model in __import__('app.models.kline', fromlist=['KLINE_MODELS']).KLINE_MODELS.values():
            db.query(model).filter(model.symbol_id == symbol.id).delete()
        from app.models.ops import SyncTask
        db.query(SyncTask).filter(SyncTask.symbol_id == symbol.id).delete()
        from app.models.kline_quality import KlineQuality
        db.query(KlineQuality).filter(KlineQuality.symbol_id == symbol.id).delete()
        db.delete(symbol); db.commit(); db.close()
        redis = get_redis_client()
        for key in redis.scan_iter(match=f'source-history:v*:*:{symbol.id}:*'):
            redis.delete(key)


def test_akshare_only_cache_supports_paging_without_writing(history):
    db, symbol, bars, provider, policy = history
    source_history.load(db, symbol.id, '1d')
    assert kline_repo.latest_bars(db, '1d', symbol.id, 2) == bars[-2:]
    assert kline_repo.get_bars(db, '1d', symbol.id, bars[0].ts, bars[-1].ts, 3, 2) == bars[2:5]
    assert kline_repo.upsert_bars(db, '1d', symbol.id, bars) == 0
    assert sync_service._write_bars(db, '1d', symbol.id, bars) == 0
    assert db.scalar(select(func.count()).select_from(Kline1d).where(Kline1d.symbol_id == symbol.id)) == 0


def test_stored_index_history_remains_available(history):
    db, symbol, bars, provider, policy = history
    local = KlineBar(bars[0].ts, 999, 999, 999, 999, 1, 1, source='stockdb')
    assert kline_repo.upsert_bars(db, '1d', symbol.id, [local]) == 1
    db.commit()
    rows = kline_repo.latest_bars(db, '1d', symbol.id, 2)
    assert len(rows) == 1 and float(rows[0].close) == 999
    provider.fetch_kline_checked.assert_not_called()


def test_source_indicators_warm_up_before_paged_range(history):
    db, symbol, bars, provider, policy = history
    source_history.load(db, symbol.id, '1d')
    rows = indicator_service.compute_indicators(db, str(symbol.id), '1d', ['macd'],
                                                start=bars[20].ts, end=bars[-1].ts)
    all_rows = indicator_service.compute_indicators(db, str(symbol.id), '1d', ['macd'],
                                                    start=bars[0].ts, end=bars[-1].ts)
    assert rows == all_rows[20:]
    assert db.scalar(select(func.count()).select_from(Kline1d).where(Kline1d.symbol_id == symbol.id)) == 0


def test_old_akshare_rows_are_ignored_when_storage_is_off(history):
    db, symbol, bars, provider, policy = history
    source_history.load(db, symbol.id, '1d')
    db.add(Kline1d(symbol_id=symbol.id, ts=bars[-1].ts, source='akshare',
                  open=999, high=999, low=999, close=999, volume=1, amount=1))
    db.commit()
    assert kline_repo.latest_bars(db, '1d', symbol.id, 1)[0].close == bars[-1].close
    assert db.scalar(select(func.count()).select_from(Kline1d).where(Kline1d.symbol_id == symbol.id)) == 1


def test_failed_source_does_not_cache_empty_success(history):
    db, symbol, bars, provider, policy = history
    provider.fetch_kline_checked.return_value = ([], False)
    with pytest.raises(ProviderError):
        source_history.load(db, symbol.id, '1d')
    assert source_history.cached(symbol.id, '1d') is None


def test_realtime_endpoint_is_retired(client):
    assert client.get('/api/v1/snapshot', params={'symbols': '1'}).status_code == 404


def test_cache_preparation_only_calls_external_sources_and_covers_pre_2000(history):
    db, symbol, bars, provider, policy = history
    old = KlineBar(datetime(1995, 1, 3, tzinfo=UTC), 1, 2, 1, 2, 1, 1, 'akshare')
    provider.fetch_kline_checked.side_effect = lambda code, period, start, end, asset, **kw: (
        [bar for bar in [old, *bars] if start <= bar.ts <= end], True)
    source_history.load(db, symbol.id, '1d')
    assert provider.fetch_kline_checked.call_args.kwargs['external_only'] is True
    assert source_history.window(db, symbol.id, '1d', old.ts, old.ts) == [old]


def test_initial_backfill_is_distinct_and_forwards_mode_to_worker(history, client, monkeypatch):
    from app.worker.tasks.sync_tasks import kline_backfill
    db, symbol, bars, provider, policy = history
    dispatch = Mock()
    monkeypatch.setattr(kline_backfill, 'apply_async', dispatch)
    payload = dict(symbol_id=symbol.id, period='1d', start='2010-01-01T00:00:00+00:00', end='2010-02-01T00:00:00+00:00')
    keys = [f"kline-backfill:{symbol.id}:1d:{payload['start']}:{payload['end']}{suffix}" for suffix in ('', ':initial')]
    try:
        first = client.post('/api/v1/kline/backfill', json=payload)
        second = client.post('/api/v1/kline/backfill', json={**payload, 'initial': True})
        assert first.status_code == second.status_code == 200
        assert first.json()['data']['task_id'] != second.json()['data']['task_id']
        assert dispatch.call_args.kwargs['kwargs'] == {'initial': True}
    finally:
        get_redis_client().delete(*keys)


def test_chart_supplement_is_offered_only_for_supported_periods_when_enabled(history, client, monkeypatch):
    _, symbol, _, provider, policy = history
    monkeypatch.setattr("app.services.market_service.local_daily_date", lambda _: None)
    params = {"symbol": str(symbol.id), "period": "1d"}
    assert client.get("/api/v1/kline/quality", params=params).json()["data"] == {
        "status": "unknown", "can_supplement": True,
    }
    result = client.get("/api/v1/kline/quality", params={**params, "period": "1m"})
    assert result.json()["data"]["can_supplement"] is False
    policy["akshare_enabled"] = False
    assert client.get("/api/v1/kline/quality", params=params).json()["data"]["can_supplement"] is False
    provider.fetch_kline_checked.assert_not_called()

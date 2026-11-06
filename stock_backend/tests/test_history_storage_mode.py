"""Regression coverage for source-only history and the opt-in persistence path."""
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
    policy = dict(akshare_enabled=True, history_storage_enabled=False, auto_sync_enabled=False, revision=900000)
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


def test_stockdb_still_persists_and_wins_when_akshare_storage_disabled(history):
    db, symbol, bars, provider, policy = history
    local = KlineBar(bars[0].ts, 999, 999, 999, 999, 1, 1, source='stockdb')
    assert kline_repo.upsert_bars(db, '1d', symbol.id, [local]) == 1
    db.commit()
    rows = kline_repo.latest_bars(db, '1d', symbol.id, 2)
    assert len(rows) == 1 and float(rows[0].close) == 999
    provider.fetch_kline_checked.assert_not_called()


def test_opt_in_uses_persisted_history_and_policy_revision_isolates_cache(history):
    db, symbol, bars, provider, policy = history
    source_history.load(db, symbol.id, '1d')
    policy.update(history_storage_enabled=True, revision=900001)
    assert kline_repo.upsert_bars(db, '1d', symbol.id, bars) == len(bars)
    db.commit()
    assert len(kline_repo.latest_bars(db, '1d', symbol.id, 5)) == 5
    assert provider.fetch_kline_checked.call_count == 1
    assert source_history.cached(symbol.id, '1d') is None
    policy.update(history_storage_enabled=False, revision=900002)
    source_history.load(db, symbol.id, '1d')
    assert provider.fetch_kline_checked.call_count == 2


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


def test_partial_local_window_does_not_change_akshare_indicator_warmup(history):
    db, symbol, bars, provider, policy = history
    local = KlineBar(bars[30].ts, 999, 999, 999, 999, 1, 1, source='stockdb')
    kline_repo.upsert_bars(db, '1d', symbol.id, [local]); db.commit()
    source_history.load(db, symbol.id, '1d')
    window = kline_repo.get_bars(db, '1d', symbol.id, bars[20].ts, bars[-1].ts)
    indicators = indicator_service.compute_indicators(db, str(symbol.id), '1d', ['macd'],
                                                     start=bars[20].ts, end=bars[-1].ts)
    assert [bar.close for bar in window] == [row['close'] for row in indicators]
    assert window[10].close != 999


def test_failed_source_does_not_cache_empty_success(history):
    db, symbol, bars, provider, policy = history
    provider.fetch_kline_checked.return_value = ([], False)
    with pytest.raises(ProviderError):
        source_history.load(db, symbol.id, '1d')
    assert source_history.cached(symbol.id, '1d') is None


def test_attention_warmup_prepares_cache_without_persisting(history):
    db, symbol, bars, provider, policy = history
    result = sync_service.run_kline_init(symbol_id=symbol.id)
    assert result[symbol.code]['1d'] == 0
    assert source_history.cached(symbol.id, '1w')
    assert db.scalar(select(func.count()).select_from(Kline1d).where(Kline1d.symbol_id == symbol.id)) == 0


def test_automatic_sync_defaults_to_no_work(monkeypatch):
    from app.worker.tasks.sync_tasks import local_market_after_close
    from app.services import local_market_sync
    monkeypatch.setattr(market_policy, 'read', lambda: {'auto_sync_enabled': False})
    request = Mock()
    monkeypatch.setattr(local_market_sync, 'request_sync', request)
    assert 'skipped' in local_market_after_close()
    request.assert_not_called()


def test_realtime_endpoint_is_retired(client):
    assert client.get('/api/v1/snapshot', params={'symbols': '1'}).status_code == 404


def test_admin_policy_switches_are_independent(client):
    from app.main import app
    from app.api.deps import get_current_admin
    original = market_policy.read()
    app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(is_admin=True)
    try:
        response = client.put('/api/v1/admin/market-source-policy', json={
            'akshare_enabled': False, 'history_storage_enabled': True, 'auto_sync_enabled': False})
        assert response.status_code == 200
        result = response.json()['data']
        assert result['akshare_enabled'] is False and result['history_storage_enabled'] is True
        assert 'snapshots_enabled' not in result
    finally:
        market_policy.save(original['akshare_enabled'], original['history_storage_enabled'], original['auto_sync_enabled'])
        app.dependency_overrides.pop(get_current_admin)


def test_watchlist_task_completes_when_akshare_is_cached_not_inserted(history):
    from app.worker.tasks.sync_tasks import watchlist_stock_sync
    from app.models.ops import SyncTask
    db, symbol, bars, provider, policy = history
    task_id = str(uuid4())
    task = SyncTask(task_type='kline_init', symbol_id=symbol.id, status='queued',
                    publish_status='published', celery_task_id=task_id)
    db.add(task); db.commit()
    result = watchlist_stock_sync.apply(kwargs={'symbol_id': symbol.id, 'initialize': True}, task_id=task_id)
    assert result.successful(), result.result
    db.expire_all()
    task = db.get(SyncTask, task.id)
    assert task.status == 'success' and task.publish_status == 'completed'
    assert source_history.cached(symbol.id, '1d')
    assert db.scalar(select(func.count()).select_from(Kline1d).where(Kline1d.symbol_id == symbol.id)) == 0


def test_cold_reads_and_startup_warmup_never_fetch_a_provider(history, monkeypatch):
    db, symbol, bars, provider, policy = history
    monkeypatch.setattr('app.repositories.symbol_repo.list_fixed_indices', lambda db: [symbol])
    assert kline_repo.latest_bars(db, '1d', symbol.id) == []
    assert kline_repo.get_bars(db, '1d', symbol.id, bars[0].ts, bars[-1].ts) == []
    assert sync_service.warmup_fixed_indices_cache()['kline_warmed'] == 0
    provider.fetch_kline_checked.assert_not_called()
    # The existing missing-history task still tries StockDB first and persists it.
    provider.fetch_kline.return_value = [KlineBar(**{**vars(bar), 'source': 'stockdb'}) for bar in bars]
    provider.fetch_kline_all.return_value = provider.fetch_kline.return_value
    sync_service.run_kline_init(symbol_id=symbol.id)
    assert db.scalar(select(func.count()).select_from(Kline1d).where(Kline1d.symbol_id == symbol.id)) == len(bars)
    assert kline_repo.latest_bars(db, '1d', symbol.id)[-1].source == 'stockdb'
    provider.fetch_kline_checked.assert_not_called()


def test_cache_preparation_only_calls_external_sources_and_covers_pre_2000(history):
    db, symbol, bars, provider, policy = history
    old = KlineBar(datetime(1995, 1, 3, tzinfo=UTC), 1, 2, 1, 2, 1, 1, 'akshare')
    provider.fetch_kline_checked.side_effect = lambda code, period, start, end, asset, **kw: (
        [bar for bar in [old, *bars] if start <= bar.ts <= end], True)
    source_history.load(db, symbol.id, '1d')
    assert provider.fetch_kline_checked.call_args.kwargs['external_only'] is True
    assert source_history.window(db, symbol.id, '1d', old.ts, old.ts) == [old]


@pytest.mark.parametrize('source', ['stockdb', 'akshare'])
def test_backtest_worker_prepares_cold_window_using_source_policy(history, monkeypatch, source):
    from app.services import backtest_service
    db, symbol, bars, provider, policy = history
    fetched = [KlineBar(**{**vars(bar), 'source': source}) for bar in bars]
    provider.fetch_kline_checked.return_value = (fetched, True)
    monkeypatch.setattr('app.data_providers.factory.get_provider', lambda: provider)
    task = SimpleNamespace(symbol_id=symbol.id, period='1d', start_ts=bars[0].ts, end_ts=bars[-1].ts)
    rows = backtest_service._load_backtest_bars(db, task, symbol)
    assert [float(bar.close) for bar in rows] == [bar.close for bar in bars]
    assert rows[-1].source == source
    count = db.scalar(select(func.count()).select_from(Kline1d).where(Kline1d.symbol_id == symbol.id))
    assert count == (len(bars) if source == 'stockdb' else 0)


@pytest.mark.parametrize('period', ['1d', '1w', '1mon'])
def test_backtest_rebases_entire_existing_local_range_under_lock(history, period):
    from sqlalchemy import text
    from app.services import backtest_service
    db, symbol, bars, provider, policy = history
    first = datetime(2020, 1, 31, tzinfo=UTC)
    last = datetime(2020, 3, 31, tzinfo=UTC)
    old = KlineBar(last, 100, 100, 100, 100, 1, 1, 'stockdb')
    kline_repo.upsert_bars(db, period, symbol.id, [old]); db.commit()
    refreshed = [KlineBar(ts, 50, 50, 50, 50, 1, 1, 'stockdb') for ts in (first, last)]
    def fetch(code, requested_period, start, end, asset):
        assert (requested_period, start, end) == (period, first, last)
        with get_session() as other:
            assert other.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),
                                {'key': 5000000000 + symbol.id}) is False
        return refreshed, True
    provider.fetch_kline_checked.side_effect = fetch
    task = SimpleNamespace(symbol_id=symbol.id, period=period, start_ts=first, end_ts=first)
    rows = backtest_service._load_backtest_bars(db, task, symbol)
    assert len(rows) == 1 and float(rows[0].close) == 50
    assert float(kline_repo.latest_bars(db, period, symbol.id, 1)[0].close) == 50


def test_window_rejects_incomplete_qfq_refresh_without_changing_stored_prices(history):
    db, symbol, bars, provider, policy = history
    old = KlineBar(bars[-1].ts, 100, 100, 100, 100, 1, 1, 'stockdb')
    kline_repo.upsert_bars(db, '1d', symbol.id, [old]); db.commit()
    provider.fetch_kline_checked.return_value = ([KlineBar(bars[0].ts, 50, 50, 50, 50, 1, 1, 'stockdb')], True)
    with pytest.raises(RuntimeError, match='未覆盖库中已有历史'):
        sync_service.prepare_history_window(db, symbol, '1d', bars[0].ts, bars[0].ts)
    db.rollback()
    assert float(kline_repo.latest_bars(db, '1d', symbol.id, 1)[0].close) == 100


@pytest.mark.parametrize('source', ['stockdb', 'akshare'])
@pytest.mark.parametrize('confirmed', [True, False])
@pytest.mark.parametrize('period', ['1d', '1w', '1mon'])
def test_initial_empty_window_finds_long_inactive_history(history, source, confirmed, period):
    from app.worker.tasks.sync_tasks import kline_backfill
    from app.utils.market_cache import as_utc
    db, symbol, bars, provider, policy = history
    old = [KlineBar(datetime(2010, 1, 4, tzinfo=UTC), 5, 6, 4, 5, 1, 1, source)]
    provider.fetch_kline_checked.side_effect = lambda code, period, start, end, asset, **kw: (
        ([bar for bar in old if start <= bar.ts <= end], True) if start == source_history.FIRST else ([], confirmed))
    job = kline_backfill.apply(kwargs=dict(symbol_id=symbol.id, period=period,
                                          start_iso=bars[0].ts.isoformat(), end_iso=bars[-1].ts.isoformat(), initial=True))
    assert job.successful(), job.result
    result = job.result
    assert result['fetched'] == 1 and result['confirmed_empty'] is False
    loaded = kline_repo.latest_bars(db, period, symbol.id)
    assert len(loaded) == 1 and as_utc(loaded[0].ts) == old[0].ts
    assert indicator_service.compute_indicators(db, str(symbol.id), period, ['macd'])
    from app.models.kline import KLINE_MODELS
    model = KLINE_MODELS[period]
    count = db.scalar(select(func.count()).select_from(model).where(model.symbol_id == symbol.id))
    assert count == (1 if source == 'stockdb' else 0)


def test_ordinary_empty_page_does_not_expand_to_all_history(history):
    db, symbol, bars, provider, policy = history
    provider.fetch_kline_checked.return_value = ([], True)
    result = sync_service.prepare_history_window(db, symbol, '1d', bars[0].ts, bars[-1].ts)
    assert result['confirmed_empty'] is True
    assert provider.fetch_kline_checked.call_count == 1


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


def test_cache_write_failure_prevents_task_completion(history, monkeypatch):
    from app.worker.tasks.sync_tasks import watchlist_stock_sync
    from app.models.ops import SyncTask
    db, symbol, bars, provider, policy = history
    redis = get_redis_client()
    monkeypatch.setattr(redis, 'lock', lambda *a, **kw: SimpleNamespace(acquire=lambda: True, release=lambda: None))
    monkeypatch.setattr(redis, 'set', Mock(side_effect=ConnectionError('Redis unavailable')))
    task_id = str(uuid4())
    task = SyncTask(task_type='kline_init', symbol_id=symbol.id, status='queued',
                    publish_status='published', celery_task_id=task_id)
    db.add(task); db.commit()
    result = watchlist_stock_sync.apply(kwargs={'symbol_id': symbol.id, 'initialize': True}, task_id=task_id)
    assert result.failed()
    db.expire_all()
    task = db.get(SyncTask, task.id)
    assert task.status != 'success' and task.publish_status != 'completed'
    assert source_history.cached(symbol.id, '1d') is None


@pytest.mark.parametrize('status,ready,requested,expected,queued', [
    ('success', True, True, 'done', False),
    ('success', False, True, 'pending', True),
    ('failed', False, True, 'pending', True),
    ('failed', False, False, 'failed', False),
    ('queued', False, True, 'pending', False),
])
def test_new_attention_distinguishes_old_delivery_states(monkeypatch, status, ready, requested, expected, queued):
    from app.services import user_service, watchlist_delivery, kline_quality_service
    now = datetime.now(UTC)
    db = Mock()
    db.scalars.return_value = [SimpleNamespace(status=status, last_run_at=now)]
    entry = SimpleNamespace(sync_status='pending', last_synced_at=None)
    sym = SimpleNamespace(id=1)
    quality = SimpleNamespace(status='complete', checked_to=now.date(), checked_at=now) if ready else None
    monkeypatch.setattr(kline_quality_service, 'get_quality', lambda *a: quality)
    monkeypatch.setattr(kline_repo, 'latest_ts', lambda *a: now if ready else None)
    queue = Mock()
    monkeypatch.setattr(watchlist_delivery, 'queue_watchlist_sync', queue)
    user_service._queue_watchlist_stock(db, entry, sym, requested=requested)
    assert entry.sync_status == expected
    assert queue.called is queued
    if queued:
        assert queue.call_args.kwargs['force'] is True

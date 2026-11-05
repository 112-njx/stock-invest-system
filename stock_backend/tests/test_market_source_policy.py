from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from app.data_providers.base import KlineBar, ProviderError
from app.data_providers.factory import DataProviderFactory, ProviderCircuit
from app.services import market_policy


def test_policy_defaults_and_snapshot_dependency():
    original = market_policy.read()
    try:
        assert market_policy.save(False, False)['akshare_enabled'] is False
        with pytest.raises(ValueError):
            market_policy.save(False, True)
        assert not market_policy.snapshots_enabled()
        assert market_policy.save(True, True)['snapshots_enabled'] is True
        assert market_policy.snapshots_enabled()
    finally:
        market_policy.save(original['akshare_enabled'], original['snapshots_enabled'])


@pytest.mark.parametrize('enabled', [False, True])
def test_fallback_switch_is_checked_per_call(monkeypatch, enabled):
    import threading
    local = SimpleNamespace(name='stockdb', can_fetch_kline=lambda *a: True,
                            fetch_kline=Mock(side_effect=ProviderError('offline')))
    remote = SimpleNamespace(name='eastmoney', can_fetch_kline=lambda *a: True,
                             fetch_kline=Mock(return_value=[KlineBar(datetime.now(UTC), 1, 1, 1, 1, 1, 1)]))
    f = DataProviderFactory.__new__(DataProviderFactory)
    f._providers = [local, remote]
    f._circuits = {p.name: ProviderCircuit(3, 60) for p in f._providers}
    f._lock = threading.Lock()
    monkeypatch.setattr(market_policy, 'akshare_enabled', lambda: enabled)
    result = f.fetch_kline('600519', '1d', datetime.now(UTC), datetime.now(UTC))
    assert bool(result) is enabled
    assert remote.fetch_kline.called is enabled
    if result:
        assert result[0].source == 'akshare'


def test_local_mode_does_not_import_or_initialize_akshare(monkeypatch):
    from app.data_providers import factory
    loader = Mock(side_effect=AssertionError('external dependencies must stay unloaded'))
    monkeypatch.setattr(factory, 'import_module', loader)
    monkeypatch.setattr(market_policy, 'akshare_enabled', lambda: False)
    source = DataProviderFactory()
    health = source.health()
    assert any(row['name'] == 'eastmoney' and row['state'] == 'disabled' for row in health)
    loader.assert_not_called()


def test_sources_coexist_without_splicing_and_week_month_are_stored(monkeypatch):
    from app.models.symbol import Symbol
    from app.models.kline import KLINE_MODELS
    from app.repositories import kline_repo
    from app.services import market_service
    from app.utils.db import get_session
    from sqlalchemy import delete
    db = get_session()
    try:
        symbol = Symbol(code='999991', name='source_test_'+uuid4().hex, type='stock', market='SSE')
        db.add(symbol)
        db.flush()
        for period in ('1d', '1w', '1mon'):
            first, last = datetime(2026, 10, 30, tzinfo=UTC), datetime(2026, 11, 5, tzinfo=UTC)
            kline_repo.upsert_bars(db, period, symbol.id, [KlineBar(first, 1, 1, 1, 1, 100, 1)])
            kline_repo.upsert_bars(db, period, symbol.id, [KlineBar(first, 10, 10, 10, 10, 100, 1, 'akshare'),
                                                        KlineBar(last, 20, 20, 20, 20, 100, 1, 'akshare')])
            for enabled in (False, True):
                monkeypatch.setattr(market_policy, 'akshare_enabled', lambda: enabled)
                rows = kline_repo.latest_bars(db, period, symbol.id)
                assert [float(row.close) for row in rows] == [1]
            rows = market_service.get_kline(db, str(symbol.id), period, first, last)
            assert [row['close'] for row in rows] == [10, 20]
        for model in KLINE_MODELS.values():
            db.execute(delete(model).where(model.symbol_id == symbol.id, model.source == 'stockdb'))
        monkeypatch.setattr(market_policy, 'akshare_enabled', lambda: False)
        assert kline_repo.latest_bars(db, '1w', symbol.id) == []
        monkeypatch.setattr(market_policy, 'akshare_enabled', lambda: True)
        assert len(kline_repo.latest_bars(db, '1w', symbol.id)) == 2
    finally:
        db.rollback()
        db.close()


def test_fallback_window_and_indicator_warmup_use_the_same_source(monkeypatch):
    from app.models.symbol import Symbol
    from app.repositories import kline_repo
    from app.services import indicator_service, market_service
    from app.utils.db import get_session
    db = get_session()
    try:
        symbol = Symbol(code='999993', name='window_source_'+uuid4().hex, type='stock', market='SSE')
        db.add(symbol)
        db.flush()
        old, recent = datetime(2020, 1, 10, tzinfo=UTC), datetime(2026, 11, 5, tzinfo=UTC)
        first, last = datetime(2020, 1, 1, tzinfo=UTC), datetime(2020, 1, 31, tzinfo=UTC)
        for period in ('1d', '1w', '1mon'):
            kline_repo.upsert_bars(db, period, symbol.id, [KlineBar(recent, 1, 1, 1, 1, 100, 1)])
            kline_repo.upsert_bars(db, period, symbol.id, [KlineBar(old, 10, 10, 10, 10, 100, 1, 'akshare')])
            monkeypatch.setattr(market_policy, 'akshare_enabled', lambda: False)
            assert market_service.get_kline(db, str(symbol.id), period, first, last) == []
            monkeypatch.setattr(market_policy, 'akshare_enabled', lambda: True)
            assert market_service.get_kline(db, str(symbol.id), period, first, last)[0]['close'] == 10
            assert kline_repo.latest_bars(db, period, symbol.id)[0].source == 'stockdb'

        # A local warmup bar outside a remote-only requested window must not
        # change the source used to compute the indicators shown on that chart.
        tail = datetime(2026, 11, 6, tzinfo=UTC)
        kline_repo.upsert_bars(db, '1d', symbol.id, [KlineBar(tail, 20, 20, 20, 20, 100, 1, 'akshare')])
        monkeypatch.setattr(indicator_service, '_get_cache', lambda *a: None)
        monkeypatch.setattr(indicator_service, '_set_cache', lambda *a: None)
        rows = indicator_service.compute_indicators(db, str(symbol.id), '1d', ['macd'], start=tail, end=tail)
        assert [row['close'] for row in rows] == [20]
    finally:
        db.rollback()
        db.close()


@pytest.mark.parametrize('asset_type', ['stock', 'etf'])
@pytest.mark.parametrize('missing_period', ['1w', '1mon'])
def test_stock_sdk_failure_aborts_initialization_before_any_write(monkeypatch, asset_type, missing_period):
    from app.services import sync_service
    bar = KlineBar(datetime(2026, 11, 5, tzinfo=UTC), 1, 2, 1, 2, 100, 200)
    provider = SimpleNamespace(fetch_kline=lambda code, period, *args: [] if period == missing_period else [bar])
    db = Mock()
    db.execute.return_value.one.return_value = (None, None)
    write = Mock()
    monkeypatch.setattr(sync_service, '_write_bars', write)
    symbol = SimpleNamespace(id=1, code='300502', name='example', type=asset_type, market='SZSE')
    with pytest.raises(RuntimeError, match=missing_period):
        sync_service._sync_symbol_klines(db, provider, symbol, bar.ts, bar.ts, False)
    write.assert_not_called()


@pytest.mark.parametrize('previous', [10, 0, None])
def test_stored_industry_quote_restores_amplitude(monkeypatch, previous):
    from app.services import local_quotes
    from app.repositories import kline_repo
    latest = SimpleNamespace(ts=datetime(2026, 11, 5, tzinfo=UTC), open=10, close=11,
                             high=12, low=9, volume=100, amount=1000, source='stockdb')
    bars = [latest] if previous is None else [SimpleNamespace(close=previous), latest]
    monkeypatch.setattr(kline_repo, 'latest_bars', lambda *a, **kw: bars)
    result = local_quotes.stored_quote(None, SimpleNamespace(id=1))
    assert result['amplitude'] == (30 if previous else None)


def test_snapshots_disabled_even_for_direct_service_calls(monkeypatch):
    from app.services import sync_service, market_service, local_quotes
    monkeypatch.setattr(market_policy, 'snapshots_enabled', lambda: False)
    provider = Mock(side_effect=AssertionError('must not fetch snapshots'))
    monkeypatch.setattr(sync_service, 'get_provider', provider)
    assert sync_service.run_realtime_poll()['skipped'] == 'snapshots disabled'
    db = Mock()
    db.scalars.return_value = []
    monkeypatch.setattr(local_quotes, 'quotes', lambda *a: [])
    monkeypatch.setattr(market_service, '_legacy_snapshots', provider)
    assert market_service.get_snapshots(db, [1]) == []


def test_official_sdk_frequency_and_qfq_are_not_reaggregated(monkeypatch):
    from app.data_providers.stockdb import StockDBProvider
    client = Mock()
    client.get.return_value.json.return_value = [dict(date=20261105, open=1, high=4, low=1, close=3, volume=1000, amount=3000)]
    context = Mock()
    context.__enter__ = Mock(return_value=client)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr('app.data_providers.stockdb.httpx.Client', lambda **kw: context)
    for period, frequency in [('1w','1w'), ('1mon','1M')]:
        rows = StockDBProvider().fetch_kline('300502', period, datetime(2026,11,1,tzinfo=UTC), datetime(2026,11,6,tzinfo=UTC))
        assert client.get.call_args.kwargs['params']['frequency'] == frequency
        assert rows[0].close == 3
        assert rows[0].volume == 10


@pytest.mark.parametrize('period', ['1w', '1mon'])
def test_advancing_sdk_period_replaces_its_old_label(period):
    from app.models.symbol import Symbol
    from app.repositories import kline_repo
    from app.utils.db import get_session
    db = get_session()
    try:
        symbol = Symbol(code='999992', name='period_label_'+uuid4().hex, type='stock', market='SSE')
        db.add(symbol)
        db.flush()
        old, new = datetime(2026, 11, 4, tzinfo=UTC), datetime(2026, 11, 5, tzinfo=UTC)
        kline_repo.upsert_bars(db, period, symbol.id, [KlineBar(old, 1, 2, 1, 2, 100, 200)])
        kline_repo.upsert_bars(db, period, symbol.id, [KlineBar(old, 1, 2, 1, 2, 100, 200),
                                                    KlineBar(new, 1, 3, 1, 3, 200, 500)])
        rows = kline_repo.latest_bars(db, period, symbol.id)
        assert len(rows) == 1
        assert rows[0].ts.date() == new.date()
        assert float(rows[0].close) == 3
    finally:
        db.rollback()
        db.close()


def test_native_long_history_index_levels_fit_storage():
    from app.models.symbol import Symbol
    from app.repositories import kline_repo
    from app.utils.db import get_session
    db = get_session()
    try:
        symbol = Symbol(code='801999.SL', name='large_index_'+uuid4().hex, type='index', market='SW')
        db.add(symbol)
        db.flush()
        stamp = datetime(2026, 11, 5, tzinfo=UTC)
        for period in ('1d', '1w', '1mon'):
            kline_repo.upsert_bars(db, period, symbol.id, [KlineBar(stamp, 1e12, 2e12, 1e12, 1.5e12, 100, 1000)])
            assert float(kline_repo.latest_bars(db, period, symbol.id)[0].close) == 1.5e12
    finally:
        db.rollback()
        db.close()


def test_policy_endpoints_require_admin(client):
    assert client.get('/api/v1/admin/market-source-policy').status_code == 401
    assert client.put('/api/v1/admin/market-source-policy', json={'akshare_enabled': True}).status_code == 401


def test_manual_sync_offline_fails_before_external_fallback(monkeypatch):
    from app.services import local_market_sync
    row = SimpleNamespace(celery_task_id='local-only', status='queued')
    db = Mock()
    db.scalar.return_value = row
    monkeypatch.setattr(local_market_sync, 'get_session', lambda: db)
    connection = Mock()
    connection.execute.return_value.scalar.return_value = True
    monkeypatch.setattr('app.utils.db.engine.connect', lambda: connection)
    monkeypatch.setattr('app.repositories.ops_repo.upsert_sync_status', Mock())
    monkeypatch.setattr(market_policy, 'akshare_enabled', lambda: False)
    monkeypatch.setattr('app.data_providers.stockdb.StockDBProvider.latest_day', Mock(side_effect=ProviderError('offline')))
    fallback = Mock()
    monkeypatch.setattr('app.data_providers.factory.get_provider', fallback)
    with pytest.raises(RuntimeError, match='AkShare'):
        local_market_sync.run('local-only')
    fallback.assert_not_called()
    assert row.status == 'failed'


@pytest.mark.asyncio
async def test_websocket_snapshot_paths_respect_policy_and_revision(monkeypatch):
    from unittest.mock import AsyncMock
    from app.api.v1 import ws_market
    broadcast = AsyncMock()
    monkeypatch.setattr(ws_market.manager, 'broadcast_snapshots', broadcast)
    monkeypatch.setattr(market_policy, 'read', lambda: dict(akshare_enabled=False, snapshots_enabled=False, revision=2))
    monkeypatch.setattr(market_policy, 'snapshots_enabled', lambda: False)
    db = Mock()
    monkeypatch.setattr(ws_market, 'get_session', db)
    await ws_market._dispatch(None, dict(type='snapshot', symbol_id=1, data={'policy_revision': 2}))
    await ws_market._handle_sync(SimpleNamespace(subscribed={1}), datetime.now(UTC).isoformat())
    db.assert_not_called()
    broadcast.assert_not_called()
    monkeypatch.setattr(market_policy, 'read', lambda: dict(akshare_enabled=True, snapshots_enabled=True, revision=3))
    await ws_market._dispatch(None, dict(type='snapshot', symbol_id=1, data={'policy_revision': 2}))
    broadcast.assert_not_called()
    await ws_market._dispatch(None, dict(type='snapshot', symbol_id=1, data={'policy_revision': 3}))
    broadcast.assert_awaited_once()

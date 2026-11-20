from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from app.data_providers.base import KlineBar, ProviderError
from app.data_providers.factory import DataProviderFactory, ProviderCircuit
from app.services import market_policy

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


def test_industry_snapshot_reads_the_stored_daily_bars(monkeypatch):
    from app.repositories import kline_repo
    from app.services import local_quotes, source_history

    sym = SimpleNamespace(id=12, code='801010.SL', name='农林牧渔', type='index', market='SW', is_fixed_index=True)
    previous = SimpleNamespace(close=10)
    latest = SimpleNamespace(ts=datetime(2026, 11, 5, tzinfo=UTC), open=10, close=11,
                             high=12, low=9, volume=100, amount=1000, source='stockdb')
    read_bars = Mock(return_value=[previous, latest])
    monkeypatch.setattr(kline_repo, 'latest_bars', read_bars)
    monkeypatch.setattr(local_quotes, 'ready_version', lambda: None)
    monkeypatch.setattr(source_history, 'cached', Mock(side_effect=AssertionError('local bars are available')))

    quote, = local_quotes.quotes(None, [sym])

    read_bars.assert_called_once_with(None, '1d', sym.id, limit=2)
    assert quote['price'] == 11
    assert quote['change_pct'] == pytest.approx(10)
    assert quote['data_date'] == '2026-11-05'


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

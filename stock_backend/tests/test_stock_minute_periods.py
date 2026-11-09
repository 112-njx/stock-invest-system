"""Minute periods use SDK session boundaries and retain asset scope."""
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.data_providers.stockdb import StockDBProvider
from app.models.kline import KLINE_MODELS


@pytest.mark.parametrize('period', ['1m', '5m', '30m', '60m'])
def test_stock_only_and_separate_storage(period):
    provider = StockDBProvider()
    assert provider.can_fetch_kline('stock', period)
    assert not provider.can_fetch_kline('etf', period)
    assert not provider.can_fetch_kline('index', period)
    assert not provider.can_fetch_kline('sw_index', period)
    assert KLINE_MODELS[period].__tablename__ == 'kline_' + period


@pytest.mark.parametrize('period', ['1m', '5m', '30m', '60m'])
def test_sdk_qfq_and_intraday_page_crop(period):
    provider = StockDBProvider()
    start = datetime(2026, 11, 6, 2, 0, tzinfo=UTC)
    end = datetime(2026, 11, 6, 3, 0, tzinfo=UTC)
    rows = [dict(date=stamp, open=10, high=11, low=9, close=10.5,
                 volume=12300, amount=129150) for stamp in
            [20261106093000, 20261106100000, 20261106110000, 20261106113000]]
    client = MagicMock()
    client.__enter__.return_value = client
    client.get.return_value.json.return_value = rows
    with patch.object(provider, '_check_maintenance'), patch('httpx.Client', return_value=client):
        result = provider.fetch_kline('600519', period, start, end, 'stock')
    assert [bar.ts.hour for bar in result] == [2, 3]
    assert all(bar.volume == 123 for bar in result)
    assert client.get.call_args.kwargs['params'] == dict(code='600519', frequency=period,
                                                        start='20261106', end='20261106')


def test_large_indicator_history_keeps_complete_warmup(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.services import indicator_service, indicator_policy, sdk_indicators, market_service
    from app.repositories import kline_repo
    from app.data_providers.base import KlineBar
    from app.services.indicator_registry import MAX_HISTORY_ROWS
    stamp = datetime(2026, 11, 6, 2, tzinfo=UTC)
    bars = [KlineBar(stamp, 10, 11, 9, 10, 100, 1000)] * 100001
    query = Mock(return_value=bars)
    monkeypatch.setattr(kline_repo, 'get_bars', query)
    monkeypatch.setattr(market_service, 'resolve_symbol_id', lambda *args: 125)
    monkeypatch.setattr(indicator_policy, 'read', lambda: {'pandas_enabled': False, 'revision': 1})
    monkeypatch.setattr(indicator_service, '_get_cache', lambda *args: None)
    monkeypatch.setattr(indicator_service, '_set_cache', lambda *args: None)
    calculate = Mock(side_effect=lambda rows, *args: [{**row, 'macd_dif': 1.} for row in rows])
    monkeypatch.setattr(sdk_indicators, 'calculate', calculate)
    db = Mock()
    db.get.return_value = SimpleNamespace(type='stock')
    rows = indicator_service.compute_indicators(db, '125', '1m', ['macd'], limit=1000)
    assert len(rows) == 1000
    assert len(calculate.call_args.args[0]) == 100001
    assert query.call_args.kwargs['limit'] == MAX_HISTORY_ROWS + 1


def test_indicator_history_over_capacity_is_not_silently_truncated(monkeypatch):
    from app.services import indicator_service, market_service
    from app.repositories import kline_repo
    from unittest.mock import Mock
    monkeypatch.setattr(indicator_service, 'MAX_HISTORY_ROWS', 2)
    monkeypatch.setattr(market_service, 'resolve_symbol_id', lambda *args: 125)
    monkeypatch.setattr(kline_repo, 'get_bars', lambda *args, **kwargs: [object()] * 3)
    with pytest.raises(ValueError, match='不能截断'):
        indicator_service.compute_indicators(Mock(), '125', '1d', ['macd'])

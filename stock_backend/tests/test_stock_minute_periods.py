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

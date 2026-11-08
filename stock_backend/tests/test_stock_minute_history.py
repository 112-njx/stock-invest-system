from datetime import date
from unittest.mock import MagicMock, patch
import pytest
from app.services import stock_minute_history as service


def row(stamp, price=10, volume=100, amount=1000):
    return dict(code='000001', date=stamp, close=price, volume=volume, amount=amount)


def test_daily_vwap_resets_and_auction_is_excluded():
    result = service.normalize([row(20261106092500, amount=999999), row(20261106093000),
                                row(20261106093100, price=12, amount=1200),
                                row(20261107130000, price=20, amount=2000)])
    assert [r['average'] for r in result] == [10, 11, 20]
    assert sum(r['volume'] for r in result) == 300


def test_missing_volume_does_not_become_zero_or_invent_average():
    result = service.normalize([row(20261106093000, volume=None), row(20261106093100), row(20261107093000)])
    assert result[0]['volume'] is None
    assert [r['average'] for r in result] == [None, None, 10]


def test_history_queries_only_requested_window():
    with patch.object(service, '_client', return_value=MagicMock()), patch.object(service, '_rd', side_effect=[['分钟k:000001:20261106150000'], [row(20261106093000)], [{'code': '000001', 'pre_close': 9}]]) as query:
        result = service.load('000001', date(2026, 11, 1), date(2026, 11, 6))
    assert query.call_args_list[1].kwargs['k2'] == 'fwd:20261101000000,20261106235959'
    assert result['latest'] == 20261106
    assert result['previous'] == 9


def test_bound_and_missing_history():
    with patch.object(service, '_client', return_value=MagicMock()), patch.object(service, '_rd', return_value=['分钟k:000001:20261106150000']):
        with pytest.raises(ValueError):
            service.load('000001', date(2026, 1, 1), date(2026, 11, 6))
    with patch.object(service, '_client', return_value=MagicMock()), patch.object(service, '_rd', return_value=[]):
        assert service.load('000001')['rows'] == []


def test_weekend_end_uses_last_valid_minute_day_for_baseline():
    with patch.object(service, '_client', return_value=MagicMock()), patch.object(service, '_rd', side_effect=[['分钟k:000001:20261106150000'], [row(20261106150000), row(20261108092500)], [{'code': '000001', 'pre_close': 9}]]) as query:
        result = service.load('000001', date(2026, 11, 1), date(2026, 11, 8))
    assert query.call_args_list[-1].kwargs['k2'] == 'qz:20261106'
    assert result['previous'] == 9
    assert result['baseline_date'] == 20261106
    assert result['end'] == '2026-11-08'


def test_empty_window_does_not_query_unrelated_daily_baseline():
    with patch.object(service, '_client', return_value=MagicMock()), patch.object(service, '_rd', side_effect=[['分钟k:000001:20261106150000'], []]) as query:
        result = service.load('000001', date(2026, 11, 7), date(2026, 11, 8))
    assert result['baseline_date'] is None
    assert result['previous'] is None
    assert query.call_count == 2

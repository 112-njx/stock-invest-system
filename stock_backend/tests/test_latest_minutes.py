from unittest.mock import MagicMock, patch
from app.services import stockdb_service as service


def test_latest_minutes_reads_only_actual_latest_session():
    client = MagicMock()
    bars = [[20260825150000, 2, 2, 2, 2, 100, 200, 0]]
    with patch.object(service, '_client', return_value=client), patch.object(service, '_rd', side_effect=[['分钟k:830001:20260825150000'], [{'code': '830001', 'pre_close': 1.9}]]) as query, patch.object(service, 'minutes', return_value=bars) as minutes:
        result = service.latest_minutes('830001')
    minutes.assert_called_once_with('830001', 20260825)
    assert result == {'date': 20260825, 'bars': bars, 'previous': 1.9}
    assert query.call_args_list[0].kwargs['num'] == -1
    assert query.call_args_list[1].kwargs['k2'] == 'qz:20260825'


def test_missing_minutes_does_not_invent_date_or_bars():
    with patch.object(service, '_client', return_value=MagicMock()), patch.object(service, '_rd', return_value=[]), patch.object(service, 'minutes') as minutes:
        assert service.latest_minutes('000001') == {'date': None, 'bars': [], 'previous': None}
    minutes.assert_not_called()

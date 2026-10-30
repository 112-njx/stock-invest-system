"""交易日缺口分组与收盘边界。"""

from datetime import UTC, date, datetime

from app.services.kline_quality_service import _last_completed, _ranges


def test_gap_ranges_use_trading_sessions_not_calendar_days():
    sessions = [date(2026, 9, 30), date(2026, 10, 9), date(2026, 10, 12), date(2026, 10, 13)]
    assert _ranges([sessions[1], sessions[2]], sessions) == [(sessions[1], sessions[2])]
    assert _ranges([sessions[1], sessions[3]], sessions) == [(sessions[1], sessions[1]), (sessions[3], sessions[3])]


def test_current_session_only_after_market_close():
    sessions = [date(2026, 10, 29), date(2026, 10, 30)]
    assert _last_completed(sessions, datetime(2026, 10, 30, 5, 0, tzinfo=UTC)) == sessions[0]
    assert _last_completed(sessions, datetime(2026, 10, 30, 8, 0, tzinfo=UTC)) == sessions[1]

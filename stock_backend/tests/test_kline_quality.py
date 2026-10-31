"""交易日缺口分组与收盘边界。"""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.services.kline_quality_service import _fetch_gap_bars, _last_completed, _ranges, eligible


def test_quality_only_accepts_mainland_a_share_stocks():
    def stock(code, market):
        return SimpleNamespace(type="stock", code=code, market=market, is_fixed_index=False)

    assert eligible(stock("600519", "SSE"))
    assert eligible(stock("300750", "SZSE"))
    assert eligible(stock("835185", "BSE"))
    assert not eligible(stock("900901", "SSE"))
    assert not eligible(stock("00700", "HK"))


def test_stock_gap_uses_stock_provider_chain_without_industry_source():
    bar = SimpleNamespace(ts=datetime(2026, 10, 8, tzinfo=UTC))

    class Provider:
        def fetch_kline(self, symbol, period, start, end, asset_type):
            assert (symbol, period, asset_type) == ("600519", "1d", "stock")
            return [bar]

    with patch("app.data_providers.ths.THSProvider.fetch_kline") as ths:
        assert _fetch_gap_bars(Provider(), "600519", "stock", date(2026, 10, 8), date(2026, 10, 8), {date(2026, 10, 8)}) == [bar]
        ths.assert_not_called()


def test_gap_ranges_use_trading_sessions_not_calendar_days():
    sessions = [date(2026, 9, 30), date(2026, 10, 9), date(2026, 10, 12), date(2026, 10, 13)]
    assert _ranges([sessions[1], sessions[2]], sessions) == [(sessions[1], sessions[2])]
    assert _ranges([sessions[1], sessions[3]], sessions) == [(sessions[1], sessions[1]), (sessions[3], sessions[3])]


def test_current_session_only_after_market_close():
    sessions = [date(2026, 10, 29), date(2026, 10, 30)]
    assert _last_completed(sessions, datetime(2026, 10, 30, 5, 0, tzinfo=UTC)) == sessions[0]
    assert _last_completed(sessions, datetime(2026, 10, 30, 8, 0, tzinfo=UTC)) == sessions[1]


def test_index_gap_uses_sina_before_slow_fallback():
    class Fallback:
        def fetch_kline(self, *_args):
            raise AssertionError("fallback should not be called")

    bar = SimpleNamespace(ts=datetime(2026, 10, 8, tzinfo=UTC))
    with patch("app.data_providers.sina.SinaProvider.fetch_kline", return_value=[bar]) as fetch:
        assert _fetch_gap_bars(Fallback(), "000001", "index", date(2026, 10, 8), date(2026, 10, 8), {date(2026, 10, 8)}) == [bar]
        fetch.assert_called_once()


def test_partial_fast_source_uses_fallback_for_missing_session():
    first = SimpleNamespace(ts=datetime(2026, 10, 8, tzinfo=UTC))
    second = SimpleNamespace(ts=datetime(2026, 10, 9, tzinfo=UTC))

    class Fallback:
        def fetch_kline(self, *_args):
            return [second]

    with patch("app.data_providers.sina.SinaProvider.fetch_kline", return_value=[first]):
        bars = _fetch_gap_bars(Fallback(), "000001", "index", date(2026, 10, 8), date(2026, 10, 9), {date(2026, 10, 8), date(2026, 10, 9)})
    assert {bar.ts.date() for bar in bars} == {date(2026, 10, 8), date(2026, 10, 9)}

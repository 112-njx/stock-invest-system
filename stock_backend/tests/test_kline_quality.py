"""交易日缺口分组与收盘边界。"""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.services.kline_quality_service import eligible


def test_quality_only_accepts_mainland_a_share_stocks():
    def stock(code, market):
        return SimpleNamespace(type="stock", code=code, market=market, is_fixed_index=False)

    assert eligible(stock("600519", "SSE"))
    assert eligible(stock("300750", "SZSE"))
    assert eligible(stock("835185", "BSE"))
    assert not eligible(stock("900901", "SSE"))
    assert not eligible(stock("00700", "HK"))

"""Unit tests for transformer — run with: pytest tests/test_transformer.py"""

from datetime import date
from src.akshare_ingest.transformer import validate_and_sort
from src.common.models import DailyKLine


def test_validate_filters_invalid():
    records = [
        DailyKLine(symbol="sh600519", trade_date=date(2026, 1, 5), open=100.0, high=101.0, low=99.0, close=100.5, volume=10000, turnover=1000000.0),
        DailyKLine(symbol="", trade_date=date(2026, 1, 6), open=101.0, high=102.0, low=100.0, close=101.5, volume=20000, turnover=2000000.0),
    ]
    valid = validate_and_sort(records)
    assert len(valid) == 1
    assert valid[0].symbol == "sh600519"


def test_validate_sorts_by_date():
    records = [
        DailyKLine(symbol="sh600519", trade_date=date(2026, 1, 7), open=102.0, high=103.0, low=101.0, close=102.5, volume=30000, turnover=3000000.0),
        DailyKLine(symbol="sh600519", trade_date=date(2026, 1, 5), open=100.0, high=101.0, low=99.0, close=100.5, volume=10000, turnover=1000000.0),
    ]
    valid = validate_and_sort(records)
    assert valid[0].trade_date == date(2026, 1, 5)
    assert valid[1].trade_date == date(2026, 1, 7)

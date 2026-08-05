"""Unit tests for AkShare fetcher — run with: pytest tests/test_fetcher.py"""

import pytest
from datetime import date
from src.akshare_ingest.fetcher import _split_symbol


def test_split_symbol_shanghai():
    prefix, code = _split_symbol("sh600519")
    assert prefix == "sh"
    assert code == "600519"


def test_split_symbol_shenzhen():
    prefix, code = _split_symbol("sz000001")
    assert prefix == "sz"
    assert code == "000001"


def test_split_symbol_invalid():
    with pytest.raises(ValueError):
        _split_symbol("xx123456")

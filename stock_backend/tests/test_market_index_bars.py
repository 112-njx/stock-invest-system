from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.data_providers.base import KlineBar, ProviderError
from app.models.symbol import Symbol
from app.repositories import market_index_repo as repo
from app.services import local_quotes, market_index_sync, market_service
from app.utils.db import get_session

STAMP = datetime(2026, 10, 12, tzinfo=UTC)


@pytest.fixture
def index():
    with get_session() as db:
        symbol = Symbol(code="000001", name="测试大盘指数独立行情", type="index", market="SSE", is_fixed_index=True)
        db.add(symbol)
        db.flush()
        yield db, symbol
        db.rollback()


def row(stamp=STAMP, source="qmt"):
    return dict(ts=stamp, open=100, high=104, low=99, close=103, pre_close=102,
                volume=123400, amount=567800, source=source)


def test_seed_preserves_public_overlap_and_respects_index_identity(index):
    db, symbol = index
    equity = SimpleNamespace(type="stock", is_fixed_index=False, code="000001", market="SZSE")
    assert not repo.handles(equity)
    assert not repo.handles(Symbol(type="index", is_fixed_index=False, code="932000", market="CSI"))
    assert repo.upsert(db, symbol, "1d", [row()], initial=True) == 1
    assert repo.upsert(db, symbol, "1d", [row(source="sina")]) == 1
    assert repo.upsert(db, symbol, "1d", [row()], initial=True) == 0
    assert repo.upsert(db, symbol, "1d", [row(source="sina")]) == 0
    assert market_service.get_kline(db, str(symbol.id), "1d")[0]["source"] == "sina"
    actual = local_quotes.quotes(db, [symbol])[0]
    assert actual["pre_close"] == 102
    assert actual["volume"] == 123400


def test_period_label_advances_without_duplicate_or_regression(index):
    db, symbol = index
    friday = STAMP + timedelta(days=4)
    assert repo.upsert(db, symbol, "1w", [row(source="eastmoney")]) == 1
    assert repo.upsert(db, symbol, "1w", [row(friday, "eastmoney")]) == 1
    assert repo.upsert(db, symbol, "1w", [row(source="eastmoney")]) == 0
    assert [bar.ts for bar in repo.bars(db, symbol.id, "1w")] == [friday]


def test_public_refresh_validates_identity_and_leaves_data_on_failure(monkeypatch):
    db = Mock()
    symbol = Symbol(id=70, code="000001", type="index", market="SSE", is_fixed_index=True)
    provider = Mock()
    provider.fetch_kline_checked.return_value = ([], False)
    monkeypatch.setattr(market_index_sync, "_public_provider", lambda: provider)
    with pytest.raises(ProviderError):
        market_index_sync.refresh_period(db, symbol, "1d", STAMP, STAMP + timedelta(days=1))
    assert not db.commit.called
    provider.fetch_kline_checked.assert_called_once_with(
        "000001", "1d", STAMP, STAMP + timedelta(days=1), "index", public_index=True,
    )
    with pytest.raises(ValueError):
        market_index_sync.refresh_period(db, Symbol(type="stock"), "1d", STAMP, STAMP)

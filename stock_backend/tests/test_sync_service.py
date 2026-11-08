"""1.5 同步服务测试：mock provider，验证 K线入库/快照/Redis 缓存/状态记录。"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from app.data_providers.base import KlineBar
from app.models.kline import KLINE_MODELS, Kline1d, Kline1mon
from app.models.symbol import Symbol
from app.services import sync_service
from app.utils.db import get_session
from app.utils.redis_client import get_redis_client


@pytest.fixture(autouse=True)
def _cleanup(monkeypatch):
    monkeypatch.setattr("app.services.market_policy.akshare_enabled", lambda: True)
    yield
    # 仅清理测试数据（名称含“测试”），不破坏种子固定指数
    db = get_session()
    test_symbol_ids = db.query(Symbol.id).filter(Symbol.name.like("测试%")).all()
    if test_symbol_ids:
        ids = [r[0] for r in test_symbol_ids]
        for model in KLINE_MODELS.values():
            db.query(model).filter(model.symbol_id.in_(ids)).delete(synchronize_session=False)
        db.query(Symbol).filter(Symbol.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    db.close()


def _make_symbol() -> Symbol:
    db = get_session()
    sym = Symbol(code="600519", name="测试贵州茅台", type="stock", market="SSE")
    db.add(sym)
    db.commit()
    db.refresh(sym)
    db.close()
    return sym


def _mock_provider() -> MagicMock:
    p = MagicMock()
    now = datetime.now(UTC)
    p.fetch_kline.return_value = [
        KlineBar(ts=now - timedelta(days=1), open=100, high=102, low=99, close=101, volume=1000, amount=1e6),
        KlineBar(ts=now, open=101, high=103, low=100, close=102, volume=1200, amount=1.2e6),
    ]
    p.resolve_index_code.return_value = "BK0447"
    return p


def test_kline_init_fetches_all_source_periods():
    sym = _make_symbol()
    provider = _mock_provider()
    daily = provider.fetch_kline.return_value
    provider.fetch_kline.side_effect = lambda symbol, period, *args: daily[-1:] if period in {"1w", "1mon"} else daily
    with patch("app.services.sync_service.get_provider", return_value=provider):
        result = sync_service.run_kline_init(symbol_id=sym.id, days=10)
    db = get_session()
    assert db.query(Kline1d).filter_by(symbol_id=sym.id).count() == 2
    assert db.query(Kline1mon).filter_by(symbol_id=sym.id).count() == 1
    assert result["600519"]["1d"] == 2
    assert {call.args[1] for call in provider.fetch_kline.call_args_list} == {"1m", "5m", "15m", "30m", "60m", "1d", "1w", "1mon"}
    db.close()


def test_kline_init_backfills_industry_code():
    db = get_session()
    sym = Symbol(code="", name="测试半导体", type="index", market="SSE", is_fixed_index=True)
    db.add(sym)
    db.commit()
    db.refresh(sym)
    db.close()
    with patch("app.services.sync_service.get_provider", return_value=_mock_provider()):
        sync_service.run_kline_init(symbol_id=sym.id, days=10)
    db = get_session()
    updated = db.get(Symbol, sym.id)
    assert updated.code == "BK0447"
    db.close()

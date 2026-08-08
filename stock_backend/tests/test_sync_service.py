"""1.5 同步服务测试：mock provider，验证 K线入库/快照/Redis 缓存/状态记录。"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from app.data_providers.base import KlineBar, RealtimeQuote
from app.models.kline import Kline1d, Kline1mon, Kline1w
from app.models.snapshot import SnapshotRealtime
from app.models.symbol import Symbol
from app.services import sync_service
from app.utils.db import get_session
from app.utils.redis_client import get_redis_client


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    # 仅清理测试数据（名称含“测试”），不破坏种子固定指数
    db = get_session()
    test_symbol_ids = db.query(Symbol.id).filter(Symbol.name.like("测试%")).all()
    if test_symbol_ids:
        ids = [r[0] for r in test_symbol_ids]
        db.query(Kline1d).filter(Kline1d.symbol_id.in_(ids)).delete(synchronize_session=False)
        db.query(Kline1w).filter(Kline1w.symbol_id.in_(ids)).delete(synchronize_session=False)
        db.query(Kline1mon).filter(Kline1mon.symbol_id.in_(ids)).delete(synchronize_session=False)
        db.query(SnapshotRealtime).filter(SnapshotRealtime.symbol_id.in_(ids)).delete(synchronize_session=False)
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
    p.fetch_realtime.return_value = [
        RealtimeQuote(
            code="600519",
            name="测试贵州茅台",
            asset_type="stock",
            price=102.0,
            change=1.0,
            change_pct=0.99,
            open=101.0,
            high=103.0,
            low=100.0,
            pre_close=101.0,
            volume=1200,
            amount=1.2e6,
            turnover=0.5,
            amplitude=1.2,
            available=True,
        )
    ]
    p.resolve_index_code.return_value = "BK0447"
    return p


def test_kline_init_upserts_all_periods_and_backfills_code():
    sym = _make_symbol()
    with patch("app.services.sync_service.get_provider", return_value=_mock_provider()):
        result = sync_service.run_kline_init(symbol_id=sym.id, days=10)
    db = get_session()
    assert db.query(Kline1d).filter_by(symbol_id=sym.id).count() == 2
    assert db.query(Kline1w).filter_by(symbol_id=sym.id).count() == 2
    assert db.query(Kline1mon).filter_by(symbol_id=sym.id).count() == 2
    assert result["600519"]["1d"] == 2
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


def test_realtime_poll_writes_snapshot_and_redis_cache():
    sym = _make_symbol()
    with patch("app.services.sync_service.get_provider", return_value=_mock_provider()):
        result = sync_service.run_realtime_poll(symbol_id=sym.id)
    assert result["synced"] == 1
    db = get_session()
    snap = db.get(SnapshotRealtime, sym.id)
    assert snap is not None and float(snap.price) == 102.0
    # sync_tasks 状态记录
    from app.models.ops import SyncTask

    st = db.query(SyncTask).filter(SyncTask.task_type == "realtime").order_by(SyncTask.id.desc()).first()
    assert st is not None and st.status == "success"
    db.close()
    assert get_redis_client().exists(f"snapshot:{sym.id}") == 1


def test_is_market_open_weekend_false():
    assert sync_service.is_market_open(datetime(2026, 8, 8, 10, 0, tzinfo=UTC)) is False  # 周六

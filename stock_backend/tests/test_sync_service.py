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


def _realtime_mock(**kwargs) -> MagicMock:
    """构造 run_realtime_poll 用的 provider mock（fetch_index_pe 默认空）。"""
    p = MagicMock()
    p.fetch_realtime.return_value = [kwargs["quote"]]
    p.fetch_index_pe.return_value = kwargs.get("index_pe", {})
    return p


def test_realtime_poll_industry_fills_from_kline():
    """行业指数基本数据补全：实时接口缺 OHLC/量/额/振幅，用日K推导。"""
    db = get_session()
    sym = Symbol(code="BK0426", name="测试油气开采", type="index", market="SSE", is_fixed_index=True)
    db.add(sym)
    db.commit()
    db.refresh(sym)
    now = datetime.now(UTC)
    db.add_all(
        [
            Kline1d(
                symbol_id=sym.id, ts=now - timedelta(days=2),
                open=2900, high=2950, low=2880, close=2920, volume=1000, amount=1e6,
            ),
            Kline1d(
                symbol_id=sym.id, ts=now - timedelta(days=1),
                open=2950, high=3050, low=2930, close=3000, volume=1200, amount=1.2e6,
            ),
        ]
    )
    db.commit()
    db.close()

    quote = RealtimeQuote(
        code="BK0426", name="测试油气开采", asset_type="industry_index",
        price=3000.0, change=5.0, change_pct=0.17, turnover=0.9,
        open=None, high=None, low=None, pre_close=None, volume=None, amount=None, amplitude=None,
        available=True,
    )
    with patch("app.services.sync_service.get_provider", return_value=_realtime_mock(quote=quote)):
        result = sync_service.run_realtime_poll(symbol_id=sym.id)
    assert result["synced"] == 1
    db = get_session()
    snap = db.get(SnapshotRealtime, sym.id)
    assert snap is not None
    assert float(snap.pre_close) == 2920.0  # 前一根 close
    assert float(snap.open) == 2950.0
    assert float(snap.high) == 3050.0
    assert float(snap.low) == 2930.0
    assert snap.volume == 1200
    assert snap.amplitude is not None and abs(float(snap.amplitude) - (3050 - 2930) / 2920 * 100) < 0.01
    db.close()


def test_realtime_poll_stock_upserts_fundamentals():
    """个股快照同步时落 stock_fundamentals（总市值/PE）。"""
    sym = _make_symbol()
    quote = RealtimeQuote(
        code="600519", name="测试贵州茅台", asset_type="stock",
        price=102.0, change=1.0, change_pct=0.99, volume=1200, amount=1.2e6,
        available=True, extra={"market_cap": 1.7e12, "pe": 25.3},
    )
    with patch("app.services.sync_service.get_provider", return_value=_realtime_mock(quote=quote)):
        result = sync_service.run_realtime_poll(symbol_id=sym.id)
    assert result["synced"] == 1
    from app.models.snapshot import StockFundamental

    db = get_session()
    fund = db.get(StockFundamental, sym.id)
    assert fund is not None and float(fund.market_cap) == 1.7e12 and float(fund.pe) == 25.3
    db.close()


def test_realtime_poll_index_upserts_valuation():
    """大盘指数快照同步时落 index_valuations（指数 PE）。"""
    db = get_session()
    sym = Symbol(code="000300", name="测试沪深300", type="index", market="CSI", is_fixed_index=True)
    db.add(sym)
    db.commit()
    db.refresh(sym)
    db.close()
    quote = RealtimeQuote(
        code="000300", name="测试沪深300", asset_type="index",
        price=4200.0, change=20.0, change_pct=0.48, available=True,
    )
    with patch(
        "app.services.sync_service.get_provider",
        return_value=_realtime_mock(quote=quote, index_pe={"测试沪深300": 12.5}),
    ):
        result = sync_service.run_realtime_poll(symbol_id=sym.id)
    assert result["synced"] == 1
    from app.models.snapshot import IndexValuation

    db = get_session()
    val = db.get(IndexValuation, sym.id)
    assert val is not None and float(val.pe) == 12.5
    db.close()


def test_realtime_poll_index_volume_none_stored_null():
    """海外指数无成交量/额字段：volume/amount 保持 NULL 而非写 0。"""
    db = get_session()
    sym = Symbol(code="DJI", name="测试道琼斯", type="index", market="US", is_fixed_index=True)
    db.add(sym)
    db.commit()
    db.refresh(sym)
    db.close()
    quote = RealtimeQuote(
        code="DJI", name="测试道琼斯", asset_type="index",
        price=40000.0, change=100.0, change_pct=0.25,
        volume=None, amount=None, available=True,
    )
    with patch(
        "app.services.sync_service.get_provider",
        return_value=_realtime_mock(quote=quote, index_pe={"测试道琼斯": None}),
    ):
        result = sync_service.run_realtime_poll(symbol_id=sym.id)
    assert result["synced"] == 1
    db = get_session()
    snap = db.get(SnapshotRealtime, sym.id)
    assert snap is not None
    assert snap.volume is None
    assert snap.amount is None
    db.close()

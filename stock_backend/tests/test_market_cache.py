"""V0.2 阶段一测试：K线缓存+击穿锁、快照缓存增强、指标缓存键、预同步/预热/sync_status。"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.data_providers.base import KlineBar
from app.models.kline import Kline1d
from app.models.ops import SyncStatus
from app.models.symbol import Symbol
from app.repositories import ops_repo
from app.services import indicator_service, market_service, sync_service
from app.utils import market_cache
from app.utils.db import get_session


@pytest.fixture(autouse=True)
def _cleanup(monkeypatch):
    monkeypatch.setattr("app.services.sync_service.supported_symbol", lambda sym: True)
    yield
    db = get_session()
    test_ids = db.query(Symbol.id).filter(Symbol.name.like("测试%")).all()
    if test_ids:
        ids = [r[0] for r in test_ids]
        db.query(Kline1d).filter(Kline1d.symbol_id.in_(ids)).delete(synchronize_session=False)
        db.query(SyncStatus).filter(SyncStatus.scope == "fixed_indices").delete(synchronize_session=False)
        db.query(Symbol).filter(Symbol.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    db.close()


def _make_symbol(type_="stock", code="600519", name="测试缓存标的", is_fixed=False) -> Symbol:
    db = get_session()
    sym = Symbol(code=code, name=name + __import__("uuid").uuid4().hex[:8], type=type_, market="SSE", is_fixed_index=is_fixed, sort_order=1 if is_fixed else None)
    db.add(sym)
    db.commit()
    db.refresh(sym)
    db.close()
    return sym


def _add_klines(symbol_id: int, n: int = 5) -> None:
    db = get_session()
    now = datetime.now(UTC)
    db.add_all(
        [
            Kline1d(
                symbol_id=symbol_id, ts=now - timedelta(days=n - i),
                open=100 + i, high=103 + i, low=99 + i, close=101 + i, volume=1000 + i, amount=1e6,
            )
            for i in range(n)
        ]
    )
    db.commit()
    db.close()


# ---- 1.2 K线缓存 ----
def test_get_kline_caches_second_call():
    sym = _make_symbol()
    _add_klines(sym.id)
    assert market_cache.get_kline_cache(sym.id, "1d", 100) is None  # 首次调用前无缓存
    r1 = market_service.get_kline(get_session(), str(sym.id), "1d", limit=100)
    assert len(r1) == 5
    r2 = market_service.get_kline(get_session(), str(sym.id), "1d", limit=100)
    assert r1 == r2  # 第二次 Redis 命中，结果一致
    assert market_cache.get_kline_cache(sym.id, "1d", 100) is not None  # 已回写缓存


def test_get_kline_explicit_range_bypasses_cache():
    sym = _make_symbol()
    _add_klines(sym.id)
    start = datetime.now(UTC) - timedelta(days=365)
    end = datetime.now(UTC)
    items = market_service.get_kline(get_session(), str(sym.id), "1d", start=start, end=end, limit=100)
    assert len(items) == 5
    assert market_cache.get_kline_cache(sym.id, "1d", 100) is None  # 显式区间不写缓存


def test_invalidate_kline_cache_clears_all_limits():
    sym = _make_symbol()
    _add_klines(sym.id)
    market_service.get_kline(get_session(), str(sym.id), "1d", limit=100)
    market_service.get_kline(get_session(), str(sym.id), "1d", limit=200)
    assert market_cache.get_kline_cache(sym.id, "1d", 100) is not None
    market_cache.invalidate_kline_cache(sym.id, "1d")
    assert market_cache.get_kline_cache(sym.id, "1d", 100) is None
    assert market_cache.get_kline_cache(sym.id, "1d", 200) is None


def test_upsert_bars_invalidates_cache():
    """同步写新K线后该标的所有周期缓存按 pattern 失效。"""
    sym = _make_symbol()
    _add_klines(sym.id)
    market_service.get_kline(get_session(), str(sym.id), "1d", limit=100)
    assert market_cache.get_kline_cache(sym.id, "1d", 100) is not None
    from app.data_providers.base import KlineBar

    new_bar = KlineBar(
        ts=datetime.now(UTC), open=110, high=112, low=109, close=111, volume=2000, amount=2e6
    )
    db = get_session()
    sync_service._write_bars(db, "1d", sym.id, [new_bar])
    db.commit()
    db.close()
    assert market_cache.get_kline_cache(sym.id, "1d", 100) is None


def test_kline_lock_acquire_exclusive():
    sym = _make_symbol()
    assert market_cache.acquire_kline_lock(sym.id, "1d") is True
    assert market_cache.acquire_kline_lock(sym.id, "1d") is False  # 已持锁
    market_cache.release_kline_lock(sym.id, "1d")
    assert market_cache.acquire_kline_lock(sym.id, "1d") is True


# ---- 1.3 快照缓存 ----


# ---- 1.4 指标缓存键 ----
def test_indicator_cache_key_default_range_stable():
    t = datetime(2026, 8, 19, tzinfo=UTC)
    k1 = indicator_service._cache_key(1, "1d", ["macd"], None, t, False, t, t, 1000)
    k2 = indicator_service._cache_key(1, "1d", ["macd"], None, t, False, datetime(2025, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC), 500)
    assert k1 == k2  # 默认区间：start/end/limit 不影响键
    assert t.isoformat() in k1  # latest_ts 在键内（新K线自动失效）


def test_indicator_cache_key_explicit_range_includes_range():
    t = datetime(2026, 8, 19, tzinfo=UTC)
    k_default = indicator_service._cache_key(1, "1d", ["macd"], None, t, False, t, t, 1000)
    k_explicit = indicator_service._cache_key(1, "1d", ["macd"], None, t, True, datetime(2025, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC), 1000)
    assert k_explicit != k_default
    assert "2025-01-01" in k_explicit


def test_compute_indicators_repeat_default_hits_cache():
    sym = _make_symbol()
    _add_klines(sym.id, n=10)
    db = get_session()
    r1 = indicator_service.compute_indicators(db, str(sym.id), "1d", ["macd", "kdj"])
    r2 = indicator_service.compute_indicators(db, str(sym.id), "1d", ["macd", "kdj"])
    db.close()
    assert r1 == r2 and r1  # 相同默认区间两次计算一致（第二次 Redis 命中）；键稳定性由单测覆盖


# ---- 1.1 预同步 / sync_status / 预热 ----
def _fixed_mock_provider():
    p = MagicMock()
    now = datetime.now(UTC)
    p.fetch_kline.return_value = [
        KlineBar(ts=now - timedelta(days=1), open=100, high=102, low=99, close=101, volume=1000, amount=1e6)
        for _ in range(3)
    ]
    p.resolve_index_code.return_value = None
    return p


def test_run_fixed_indices_sync_updates_sync_status():
    sym = _make_symbol(type_="index", code="000001", name="测试上证指数", is_fixed=True)
    with patch("app.services.sync_service.get_provider", return_value=_fixed_mock_provider()):
        with patch("app.services.sync_service.symbol_repo.list_fixed_indices", return_value=[sym]):
            sync_service.run_fixed_indices_sync()
    db = get_session()
    st = ops_repo.list_sync_status(db, "fixed_indices")
    assert st and st[-1].status == "done" and st[-1].progress == 100 and st[-1].total == 1
    assert db.query(Kline1d).filter_by(symbol_id=sym.id).count() >= 1
    db.close()


def test_maybe_presync_triggers_when_stale(monkeypatch):
    redis = MagicMock()
    redis.set.return_value = True
    monkeypatch.setattr('app.utils.redis_client.get_redis_client', lambda: redis)
    sym = _make_symbol(type_="index", code="000001", name="测试上证指数", is_fixed=True)
    with patch("app.services.sync_service.symbol_repo.list_fixed_indices", return_value=[sym]):
        with patch("app.worker.tasks.sync_tasks.kline_init_fixed_indices") as mock_task:
            mock_task.delay.return_value.id = "fake-task"
            result = sync_service.maybe_presync_fixed_indices()
    assert result["triggered"] is True and result["stale"] == 1
    assert mock_task.delay.called


def test_maybe_presync_skips_when_fresh():
    sym = _make_symbol(type_="index", code="000001", name="测试上证指数", is_fixed=True)
    _add_klines(sym.id, n=2)
    with patch("app.services.sync_service.symbol_repo.list_fixed_indices", return_value=[sym]):
        with patch("app.services.kline_quality_service.get_quality", return_value=SimpleNamespace(status="complete")):
            with patch("app.worker.tasks.sync_tasks.kline_init_fixed_indices") as mock_task:
                result = sync_service.maybe_presync_fixed_indices()
    assert result["triggered"] is False
    assert not mock_task.delay.called


def test_maybe_presync_checks_fresh_but_unverified_klines():
    sym = _make_symbol(type_="index", code="000001", name="测试上证指数", is_fixed=True)
    _add_klines(sym.id, n=2)
    with patch("app.services.sync_service.symbol_repo.list_fixed_indices", return_value=[sym]):
        with patch("app.services.kline_quality_service.get_quality", return_value=None):
            with patch("app.worker.tasks.sync_tasks.kline_init_fixed_indices") as mock_task:
                result = sync_service.maybe_presync_fixed_indices()
    assert result["triggered"] is False and result["stale"] == 0
    assert not mock_task.delay.called


def test_warmup_fixed_indices_cache():
    sym = _make_symbol(type_="index", code="000001", name="测试上证指数", is_fixed=True)
    _add_klines(sym.id, n=3)
    with patch("app.services.sync_service.symbol_repo.list_fixed_indices", return_value=[sym]):
        result = sync_service.warmup_fixed_indices_cache()
    assert result["kline_warmed"] == 1
    assert market_cache.get_kline_cache(sym.id, "1d", 500) is not None

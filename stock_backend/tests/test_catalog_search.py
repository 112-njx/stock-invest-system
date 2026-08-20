"""V0.2 阶段三测试：目录预同步、搜索三层增强、关注自动同步与缓存。"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from app.models.kline import Kline1d
from app.models.symbol import Symbol
from app.models.user import User
from app.services import market_service, sync_service
from app.utils import market_cache
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_cat_"


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    db = get_session()
    test_ids = db.query(Symbol.id).filter(Symbol.name.like("测试%")).all()
    if test_ids:
        ids = [r[0] for r in test_ids]
        db.query(Kline1d).filter(Kline1d.symbol_id.in_(ids)).delete(synchronize_session=False)
        db.query(Symbol).filter(Symbol.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    db.close()
    market_cache.invalidate_search_cache()


def _make_catalog_symbol(code: str, name: str, type_="stock") -> Symbol:
    db = get_session()
    sym = Symbol(code=code, name=name, type=type_, market="SSE", is_catalog=True)
    db.add(sym)
    db.commit()
    db.refresh(sym)
    db.close()
    return sym


# ---- 3.1 目录预同步 ----
def test_run_catalog_sync_upserts_and_writes_status():
    provider = MagicMock()
    provider.fetch_catalog.return_value = {
        "stocks": [("900001", "测试目录A股"), ("900002", "测试目录B股")],
        "etfs": [("901001", "测试目录ETF")],
    }
    with patch("app.services.sync_service.get_provider", return_value=provider):
        result = sync_service.run_catalog_sync()
    assert result["added_stocks"] == 2 and result["added_etfs"] == 1
    db = get_session()
    assert db.query(Symbol).filter_by(code="900001").first() is not None
    assert db.query(Symbol).filter_by(code="900001").first().is_catalog is True
    from app.models.ops import SyncStatus

    st = db.query(SyncStatus).filter_by(scope="catalog").order_by(SyncStatus.id.desc()).first()
    assert st is not None and st.status in ("done", "partial")
    db.close()


def test_run_catalog_sync_idempotent_second_run_no_duplicate():
    provider = MagicMock()
    provider.fetch_catalog.return_value = {"stocks": [("900001", "测试目录A股")], "etfs": []}
    with patch("app.services.sync_service.get_provider", return_value=provider):
        sync_service.run_catalog_sync()
        sync_service.run_catalog_sync()
    db = get_session()
    assert db.query(Symbol).filter_by(code="900001").count() == 1
    db.close()


def test_maybe_catalog_sync_triggers_below_threshold():
    with patch("app.services.sync_service.symbol_repo.count_catalog_stocks", return_value=100):
        with patch("app.worker.tasks.sync_tasks.catalog_sync") as mock_task:
            mock_task.delay.return_value.id = "catalog-task"
            result = sync_service.maybe_catalog_sync()
    assert result["triggered"] is True and mock_task.delay.called


def test_maybe_catalog_sync_skips_when_enough():
    with patch("app.services.sync_service.symbol_repo.count_catalog_stocks", return_value=5000):
        with patch("app.worker.tasks.sync_tasks.catalog_sync") as mock_task:
            result = sync_service.maybe_catalog_sync()
    assert result["triggered"] is False and not mock_task.delay.called


def test_admin_catalog_sync_endpoint(client: TestClient):
    uname = f"{_PREFIX}{uuid.uuid4().hex[:8]}"
    token = client.post("/api/v1/auth/register", json={"username": uname, "password": "pass123456"}).json()["data"][
        "token"
    ]
    db = get_session()
    try:
        u = db.query(User).filter(User.username == uname).first()
        u.is_admin = True
        db.commit()
    finally:
        db.close()
    try:
        with patch("app.api.v1.admin.catalog_sync") as mock_task:
            mock_task.delay.return_value.id = "cat-1"
            resp = client.post("/api/v1/admin/catalog/sync", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["data"] == {"task_id": "cat-1", "status": "queued"}
    finally:
        db = get_session()
        try:
            u = db.query(User).filter(User.username == uname).first()
            if u:
                db.delete(u)
            db.commit()
        finally:
            db.close()


# ---- 3.2 搜索三层增强 ----
def test_search_exact_code_first():
    sym = _make_catalog_symbol("900111", "测试精确标的")
    db = get_session()
    db.add(Kline1d(symbol_id=sym.id, ts=datetime.now(UTC), open=1, high=2, low=1, close=1.5, volume=1, amount=1.0))
    db.commit()
    db.close()
    rows = market_service.search_symbols(get_session(), "900111")
    assert rows and rows[0]["code"] == "900111"
    assert rows[0]["has_kline"] is True
    assert rows[0]["is_catalog"] is True


def test_search_fuzzy_prefers_synced_over_catalog():
    synced = _make_catalog_symbol("900201", "测试已同步股票")
    _make_catalog_symbol("900202", "测试仅目录股票")
    db = get_session()
    db.add(Kline1d(symbol_id=synced.id, ts=datetime.now(UTC), open=1, high=2, low=1, close=1.5, volume=1, amount=1.0))
    db.commit()
    db.close()
    rows = market_service.search_symbols(get_session(), "测试")
    codes = [r["code"] for r in rows]
    # is_catalog=FALSE（已同步）排在 is_catalog=TRUE（仅目录）之前
    assert codes.index("900201") < codes.index("900202")
    assert rows[0]["has_kline"] is True


def test_search_caches_result():
    _make_catalog_symbol("900301", "测试缓存股票")
    db = get_session()
    rows1 = market_service.search_symbols(db, "900301")
    assert rows1
    # 直接清空 Redis 之外再验证命中：缓存存在则第二次直接读缓存
    assert market_cache.get_search_cache(None, "900301") is not None
    rows2 = market_service.search_symbols(db, "900301")
    assert rows1 == rows2


def test_search_external_fallback_inserts_catalog():
    provider = MagicMock()
    provider.search_ak_stock.return_value = [("900401", "测试外部股票")]  # 命中查询词，保证重查本地可命中
    with patch("app.services.market_service.get_provider", return_value=provider):
        rows = market_service.search_symbols(get_session(), "测试外部", type_="stock")
    assert rows and rows[0]["code"] == "900401"
    db = get_session()
    assert db.query(Symbol).filter_by(code="900401").first() is not None
    assert db.query(Symbol).filter_by(code="900401").first().is_catalog is True
    db.close()


def test_search_endpoint_returns_sync_flags(client: TestClient):
    _make_catalog_symbol("900501", "测试搜索接口")
    resp = client.get("/api/v1/symbols/search", params={"q": "900501"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data and data[0]["is_catalog"] is True and "has_kline" in data[0]


# ---- 3.3 关注自动同步 ----
@pytest.fixture()
def user_token(client: TestClient) -> str:
    uname = f"{_PREFIX}w{uuid.uuid4().hex[:8]}"
    try:
        resp = client.post("/api/v1/auth/register", json={"username": uname, "password": "pass123456"})
        yield resp.json()["data"]["token"]
    finally:
        db = get_session()
        try:
            u = db.query(User).filter(User.username == uname).first()
            if u:
                db.delete(u)
            db.commit()
        finally:
            db.close()


def test_watchlist_add_catalog_symbol_triggers_kline_init(client: TestClient, user_token: str):
    sym = _make_catalog_symbol("900601", "测试关注新股")
    headers = {"Authorization": f"Bearer {user_token}"}
    with patch("app.worker.tasks.sync_tasks.kline_init") as mock_task:
        mock_task.delay.return_value = None
        resp = client.post("/api/v1/watchlist", json={"symbol": sym.code}, headers=headers)
    assert resp.status_code == 200
    row = resp.json()["data"]
    assert row["sync_status"] == "pending"  # 无K线 → 同步中
    mock_task.delay.assert_called_once_with(symbol_id=sym.id)


def test_watchlist_add_synced_symbol_marked_done(client: TestClient, user_token: str):
    sym = _make_catalog_symbol("900602", "测试关注已同步")
    db = get_session()
    db.add(Kline1d(symbol_id=sym.id, ts=datetime.now(UTC), open=1, high=2, low=1, close=1.5, volume=1, amount=1.0))
    db.commit()
    db.close()
    headers = {"Authorization": f"Bearer {user_token}"}
    with patch("app.worker.tasks.sync_tasks.kline_init") as mock_task:
        resp = client.post("/api/v1/watchlist", json={"symbol": "900602"}, headers=headers)
    assert resp.status_code == 200
    row = resp.json()["data"]
    assert row["sync_status"] == "done" and row["last_synced_at"] is not None
    assert not mock_task.delay.called


# ---- 3.4 关注缓存 ----
def test_watchlist_cache_second_call_hits(client: TestClient, user_token: str):
    sym = _make_catalog_symbol("900603", "测试缓存股票")
    headers = {"Authorization": f"Bearer {user_token}"}
    with patch("app.worker.tasks.sync_tasks.kline_init"):
        client.post("/api/v1/watchlist", json={"symbol": sym.code}, headers=headers)
    resp1 = client.get("/api/v1/watchlist", headers=headers)
    rows1 = resp1.json()["data"]
    assert rows1
    # 缓存写入
    db = get_session()
    uid = db.query(User).filter(User.username.like(f"{_PREFIX}w%")).order_by(User.id.desc()).first().id
    db.close()
    assert market_cache.get_watchlist_cache(uid) is not None
    resp2 = client.get("/api/v1/watchlist", headers=headers)
    assert resp1.json() == resp2.json()  # 第二次 Redis 命中
    # 删除后缓存失效
    rid = rows1[0]["id"]
    client.delete(f"/api/v1/watchlist/{rid}", headers=headers)
    assert market_cache.get_watchlist_cache(uid) is None


def test_snapshot_watchlist_snap_cache(client: TestClient, user_token: str):
    sym = _make_catalog_symbol("900604", "测试快照股票")
    headers = {"Authorization": f"Bearer {user_token}"}
    with patch("app.worker.tasks.sync_tasks.kline_init"):
        client.post("/api/v1/watchlist", json={"symbol": sym.code}, headers=headers)
    resp = client.get("/api/v1/snapshot", params={"symbols": str(sym.id)}, headers=headers)
    assert resp.status_code == 200
    db = get_session()
    uid = db.query(User).filter(User.username.like(f"{_PREFIX}w%")).order_by(User.id.desc()).first().id
    db.close()
    assert market_cache.get_watchlist_snap_cache(uid) is not None  # 按关注集缓存

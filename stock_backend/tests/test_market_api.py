"""1.7 行情查询 API 测试。"""

from datetime import UTC, datetime

import pytest
from app.models.kline import Kline1d
from app.models.symbol import Symbol
from app.utils.db import get_session
from fastapi.testclient import TestClient


@pytest.fixture()
def _kline_test_data():
    """写入测试标的 + 日K，测后清理。"""
    db = get_session()
    sym = Symbol(code="666666", name="测试行情标的", type="stock", market="SSE")
    db.add(sym)
    db.commit()
    db.refresh(sym)
    db.add_all(
        [
            Kline1d(
                symbol_id=sym.id,
                ts=datetime(2026, 8, 1, tzinfo=UTC),
                open=10,
                high=11,
                low=9.5,
                close=10.5,
                volume=1000,
                amount=1e6,
            ),
            Kline1d(
                symbol_id=sym.id,
                ts=datetime(2026, 8, 2, tzinfo=UTC),
                open=10.5,
                high=12,
                low=10,
                close=11.8,
                volume=1500,
                amount=1.7e6,
            ),
        ]
    )
    db.commit()
    yield sym
    db.query(Kline1d).filter(Kline1d.symbol_id == sym.id).delete()
    db.query(Symbol).filter(Symbol.id == sym.id).delete()
    db.commit()
    db.close()


def test_symbols_fixed_indices(client: TestClient):
    resp = client.get("/api/v1/symbols", params={"type": "index", "is_fixed": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert len(data) == 49
    sorts = [d["sort_order"] for d in data]
    assert sorts == sorted(sorts)


def test_symbols_search_exact_code(client: TestClient):
    resp = client.get("/api/v1/symbols/search", params={"q": "600519"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data and data[0]["code"] == "600519"


def test_kline_returns_bars(client: TestClient, _kline_test_data):
    resp = client.get("/api/v1/kline", params={"symbol": "666666", "period": "1d"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 2
    assert data[0]["close"] == 10.5
    assert data[0]["ts"]


def test_kline_invalid_period(client: TestClient):
    resp = client.get("/api/v1/kline", params={"symbol": "600519", "period": "5m"})
    assert resp.status_code == 422


def test_kline_unknown_symbol_empty(client: TestClient):
    resp = client.get("/api/v1/kline", params={"symbol": "999999", "period": "1d"})
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_snapshot_merges_symbols(client: TestClient, _kline_test_data):
    # 用测试标的（有K线无快照，不受实时库数据影响）验证：按 id 合并返回 + 无快照字段为 null
    resp = client.get("/api/v1/snapshot", params={"symbols": str(_kline_test_data.id)})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data and data[0]["code"] == "666666"
    assert data[0]["price"] is None
    assert data[0]["change"] is None


def test_snapshot_invalid_id(client: TestClient):
    resp = client.get("/api/v1/snapshot", params={"symbols": "abc"})
    assert resp.status_code == 400


def test_sync_status_no_record_returns_done(client: TestClient):
    resp = client.get("/api/v1/sync-status", params={"scope": "fixed_indices"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "done" and data["progress"] == 100 and "message" in data


def test_fetch_all_no_token(client: TestClient):
    """一次性全量同步接口：免鉴权、同步执行（mock 掉网络同步逻辑）。"""
    from unittest.mock import patch

    with (
        patch("app.services.sync_service.run_fixed_indices_sync", return_value={"000001": {"1d": 1}}) as m_fixed,
        patch("app.services.sync_service.run_realtime_poll", return_value={"synced": 1}) as m_rt,
    ):
        resp = client.post("/api/v1/fetch-all")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["fixed_indices"]["000001"]["1d"] == 1
    assert body["data"]["realtime"]["synced"] == 1
    m_fixed.assert_called_once()
    m_rt.assert_called_once()


def test_sync_status_returns_latest_record(client: TestClient):
    from datetime import UTC, datetime

    from app.models.ops import SyncStatus
    from app.utils.db import get_session

    db = get_session()
    try:
        db.add(
            SyncStatus(
                scope="fixed_indices",
                status="running",
                progress=35,
                total=49,
                message="已同步 35/49",
                started_at=datetime.now(UTC),
            )
        )
        db.commit()
    finally:
        db.close()
    try:
        resp = client.get("/api/v1/sync-status", params={"scope": "fixed_indices"})
        data = resp.json()["data"]
        assert data == {"status": "running", "progress": 35, "total": 49, "message": "已同步 35/49"}
    finally:
        db = get_session()
        try:
            db.query(SyncStatus).filter_by(scope="fixed_indices").delete()
            db.commit()
        finally:
            db.close()

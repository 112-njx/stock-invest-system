"""V0.2 阶段二测试：WS 连接鉴权、订阅模型、心跳、断线增量补拉、管理器推送。"""

import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.snapshot import SnapshotRealtime
from app.models.symbol import Symbol
from app.models.user import User
from app.utils.db import get_session
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

_PREFIX = "test_ws_"


@pytest.fixture()
def user_token(client: TestClient) -> str:
    uname = f"{_PREFIX}{uuid.uuid4().hex[:8]}"
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


def test_ws_rejects_without_token(client: TestClient):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/api/v1/ws/market"):
            pass
    assert exc.value.code == 4001


def test_ws_rejects_bad_token(client: TestClient):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/ws/market?token=bad-token"):
            pass


def test_ws_subscribe_and_heartbeat_ping(client: TestClient, user_token: str, monkeypatch):
    import app.api.v1.ws_market as ws_market

    monkeypatch.setattr(ws_market, "PING_INTERVAL", 0.1)  # 缩短心跳便于测试
    with client.websocket_connect(f"/api/v1/ws/market?token={user_token}") as ws:
        ws.send_text(json.dumps({"action": "subscribe", "symbol_ids": [1, 2, 3]}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "ping"  # 服务端心跳到达
        # 订阅集合已记录
        from app.ws.manager import manager

        user_id = manager._connections  # noqa: SLF001 测试内省
        conns = next(iter(user_id.values()))
        assert conns[0].subscribed == {1, 2, 3}


def test_ws_unsubscribe(client: TestClient, user_token: str):
    from app.ws.manager import manager

    with client.websocket_connect(f"/api/v1/ws/market?token={user_token}") as ws:
        ws.send_text(json.dumps({"action": "subscribe", "symbol_ids": [5, 6]}))
        ws.send_text(json.dumps({"action": "unsubscribe", "symbol_ids": [5]}))
        time.sleep(0.2)  # 等待服务端消费消息（无 ack，需短等待同步点）
        conns = list(manager._connections.values())[0]  # noqa: SLF001
        assert conns[0].subscribed == {6}


def test_ws_sync_catches_up_missing_snapshots(client: TestClient, user_token: str):
    """断线补拉：sync since 之后更新的快照批量返回。"""
    db = get_session()
    sym = Symbol(code="600519", name="测试WS快照", type="stock", market="SSE")
    db.add(sym)
    db.commit()
    db.refresh(sym)
    db.add(
        SnapshotRealtime(
            symbol_id=sym.id, price=100.0, change=1.0, change_pct=0.5,
            open=99.0, high=101.0, low=98.0, pre_close=99.0, volume=1000, amount=1e6,
            turnover=0.5, amplitude=1.2, updated_at=datetime.now(UTC),
        )
    )
    db.commit()
    try:
        since = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        with client.websocket_connect(f"/api/v1/ws/market?token={user_token}") as ws:
            ws.send_text(json.dumps({"action": "subscribe", "symbol_ids": [sym.id]}))
            ws.send_text(json.dumps({"action": "sync", "since": since}))
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "snapshot"
            assert str(sym.id) in msg["data"] or sym.id in msg["data"]
    finally:
        db = get_session()
        db.query(SnapshotRealtime).filter_by(symbol_id=sym.id).delete()
        db.query(Symbol).filter_by(id=sym.id).delete()
        db.commit()
        db.close()


# ---- ConnectionManager 单元测试 ----
class _FakeWS:
    def __init__(self):
        self.sent: list[str] = []

    async def accept(self):
        pass

    async def send_text(self, text: str):
        self.sent.append(text)

    async def close(self, code=1000, reason=""):
        pass


async def test_manager_broadcast_filters_by_subscription():
    from app.ws.manager import ConnectionManager

    m = ConnectionManager()
    ws1, ws2 = _FakeWS(), _FakeWS()
    s1 = await m.connect(1, ws1)
    s2 = await m.connect(2, ws2)
    s1.subscribed = {10, 11}
    s2.subscribed = {11, 12}
    await m.broadcast_snapshots({10: {"price": 1.0}, 11: {"price": 2.0}})
    m1 = json.loads(ws1.sent[0])  # 用户1 订阅 10/11 → 两条都收到
    assert m1["type"] == "snapshot" and set(m1["data"].keys()) == {"10", "11"}
    m2 = json.loads(ws2.sent[0])  # 用户2 只订阅 11 → 仅收到 11
    assert set(m2["data"].keys()) == {"11"}
    await m.disconnect(s1)
    await m.disconnect(s2)


async def test_manager_broadcast_kline_to_subscriber():
    from app.ws.manager import ConnectionManager

    m = ConnectionManager()
    ws = _FakeWS()
    s = await m.connect(1, ws)
    s.subscribed = {10}
    await m.broadcast_kline({"symbol_id": 10, "period": "15m", "bar": {"close": 1.0}})
    msg = json.loads(ws.sent[0])
    assert msg["type"] == "kline" and msg["period"] == "15m" and msg["bar"]["close"] == 1.0
    await m.disconnect(s)


async def test_manager_connect_disconnect_cleanup():
    from app.ws.manager import ConnectionManager

    m = ConnectionManager()
    ws = _FakeWS()
    s = await m.connect(7, ws)
    assert m.count() == 1
    await m.disconnect(s)
    assert m.count() == 0

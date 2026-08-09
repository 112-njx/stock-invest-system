"""3.1 会话与消息测试：创建/列表/重命名/删除、消息追加与顺序、用户隔离。"""

import uuid

from app.models.symbol import Symbol
from app.models.user import User
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_conv_"


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _cleanup_users(*usernames: str) -> None:
    db = get_session()
    try:
        for uname in usernames:
            u = db.query(User).filter(User.username == uname).first()
            if u:
                db.delete(u)
        db.commit()
    finally:
        db.close()


def _register(client: TestClient, username: str) -> str:
    resp = client.post("/api/v1/auth/register", json={"username": username, "password": "pass123456"})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _cleanup_symbol(code: str) -> None:
    db = get_session()
    try:
        sym = db.query(Symbol).filter(Symbol.code == code).first()
        if sym:
            db.delete(sym)
        db.commit()
    finally:
        db.close()


def _seed_symbol(code: str = "600600") -> int:
    db = get_session()
    sym = Symbol(code=code, name="会话测试标的", type="stock", market="SSE")
    db.add(sym)
    db.commit()
    db.refresh(sym)
    sid = sym.id
    db.close()
    return sid


def test_conversation_crud(client: TestClient):
    uname = _uname()
    try:
        token = _register(client, uname)
        h = _auth(token)

        # 创建（默认标题）
        r = client.post("/api/v1/conversations", json={}, headers=h)
        assert r.status_code == 200 and r.json()["code"] == 0
        conv_id = r.json()["data"]["id"]

        # 列表
        rows = client.get("/api/v1/conversations", headers=h).json()["data"]
        assert any(c["id"] == conv_id for c in rows)

        # 重命名
        r = client.patch(f"/api/v1/conversations/{conv_id}", json={"title": "新标题"}, headers=h)
        assert r.json()["data"]["title"] == "新标题"

        # 删除
        r = client.delete(f"/api/v1/conversations/{conv_id}", headers=h)
        assert r.json()["code"] == 0
        rows = client.get("/api/v1/conversations", headers=h).json()["data"]
        assert all(c["id"] != conv_id for c in rows)
    finally:
        _cleanup_users(uname)


def test_messages_order_and_symbol(client: TestClient):
    uname = _uname()
    code = "600601"
    try:
        token = _register(client, uname)
        h = _auth(token)
        conv_id = client.post("/api/v1/conversations", json={}, headers=h).json()["data"]["id"]
        symbol_id = _seed_symbol(code)

        # 追加两条消息，第二条绑定标的
        r1 = client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"role": "user", "content": "第一条"},
            headers=h,
        )
        r2 = client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"role": "assistant", "content": "第二条", "symbol": code, "tokens": 10},
            headers=h,
        )
        assert r1.status_code == 200 and r2.status_code == 200
        assert r2.json()["data"]["symbol_id"] == symbol_id
        assert r2.json()["data"]["tokens"] == 10

        msgs = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=h).json()["data"]
        assert [m["content"] for m in msgs] == ["第一条", "第二条"]  # 时间升序
        assert msgs[1]["symbol_id"] == symbol_id

        # 绑定不存在的标的 → 400
        r = client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"role": "user", "content": "x", "symbol": "999999"},
            headers=h,
        )
        assert r.status_code == 400
    finally:
        _cleanup_symbol(code)
        _cleanup_users(uname)


def test_conversation_ownership(client: TestClient):
    uname1, uname2 = _uname(), _uname()
    try:
        t1 = _register(client, uname1)
        t2 = _register(client, uname2)
        conv_id = client.post("/api/v1/conversations", json={"title": "私密"}, headers=_auth(t1)).json()["data"]["id"]

        # 用户2 不能访问/重命名/删除用户1 的会话
        assert client.get(f"/api/v1/conversations/{conv_id}/messages", headers=_auth(t2)).status_code == 404
        assert client.patch(f"/api/v1/conversations/{conv_id}", json={"title": "hack"}, headers=_auth(t2)).status_code == 404
        assert client.delete(f"/api/v1/conversations/{conv_id}", headers=_auth(t2)).status_code == 404
    finally:
        _cleanup_users(uname1, uname2)


def test_requires_token(client: TestClient):
    assert client.post("/api/v1/conversations", json={}).status_code == 401
    assert client.get("/api/v1/conversations").status_code == 401

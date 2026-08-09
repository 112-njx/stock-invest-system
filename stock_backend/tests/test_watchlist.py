"""2.2 重点关注股票 API 测试：添加（幂等）/列表（合并实时价）/删除。"""

import uuid

import pytest
from app.models.user import User
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_wl_"


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


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_add_list_delete(client: TestClient, user_token: str):
    headers = _auth(user_token)
    resp = client.post("/api/v1/watchlist", json={"symbol": "600519"}, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    row = body["data"]
    assert row["code"] == "600519"
    assert row["name"] == "贵州茅台"
    assert "price" in row

    lst = client.get("/api/v1/watchlist", headers=headers).json()["data"]
    assert len(lst) == 1
    assert lst[0]["symbol_id"] == row["symbol_id"]

    rid = row["id"]
    resp = client.delete(f"/api/v1/watchlist/{rid}", headers=headers)
    assert resp.status_code == 200
    assert client.get("/api/v1/watchlist", headers=headers).json()["data"] == []


def test_add_idempotent(client: TestClient, user_token: str):
    headers = _auth(user_token)
    for _ in range(2):
        resp = client.post("/api/v1/watchlist", json={"symbol": "600519"}, headers=headers)
        assert resp.status_code == 200
    lst = client.get("/api/v1/watchlist", headers=headers).json()["data"]
    assert len(lst) == 1


def test_add_by_symbol_id(client: TestClient, user_token: str):
    headers = _auth(user_token)
    resp = client.post("/api/v1/watchlist", json={"symbol": "600519"}, headers=headers)
    symbol_id = resp.json()["data"]["symbol_id"]
    resp2 = client.post("/api/v1/watchlist", json={"symbol": str(symbol_id)}, headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["data"]["symbol_id"] == symbol_id


def test_add_unknown_symbol(client: TestClient, user_token: str):
    resp = client.post("/api/v1/watchlist", json={"symbol": "999999"}, headers=_auth(user_token))
    assert resp.status_code == 400


def test_delete_other_user_isolated(client: TestClient, user_token: str):
    """多租户隔离：A 的记录 B 删不掉（user_id 强制过滤）。"""
    headers_a = _auth(user_token)
    row = client.post("/api/v1/watchlist", json={"symbol": "600519"}, headers=headers_a).json()["data"]

    uname = f"{_PREFIX}b{uuid.uuid4().hex[:8]}"
    try:
        token_b = client.post("/api/v1/auth/register", json={"username": uname, "password": "pass123456"}).json()[
            "data"
        ]["token"]
        resp = client.delete(f"/api/v1/watchlist/{row['id']}", headers=_auth(token_b))
        assert resp.status_code == 404
    finally:
        db = get_session()
        try:
            u = db.query(User).filter(User.username == uname).first()
            if u:
                db.delete(u)
            db.commit()
        finally:
            db.close()


def test_watchlist_requires_token(client: TestClient):
    assert client.get("/api/v1/watchlist").status_code == 401

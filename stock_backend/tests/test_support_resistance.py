"""2.3 支撑/压力位 API 测试：添加/列表（按标的过滤）/删除/校验。"""

import uuid

import pytest
from app.models.user import User
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_sr_"


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


def test_add_list_and_delete(client: TestClient, user_token: str):
    headers = _auth(user_token)
    resp = client.post(
        "/api/v1/support-resistance",
        json={"symbol": "600519", "type": "support", "price": 1200.0, "note": "强支撑"},
        headers=headers,
    )
    assert resp.status_code == 200
    row = resp.json()["data"]
    assert row["symbol_id"]
    assert row["type"] == "support"
    assert row["price"] == 1200.0

    resp2 = client.post(
        "/api/v1/support-resistance",
        json={"symbol": "600519", "type": "pressure", "price": 1600.0},
        headers=headers,
    )
    assert resp2.status_code == 200

    lst = client.get("/api/v1/support-resistance", params={"symbol_id": row["symbol_id"]}, headers=headers)
    data = lst.json()["data"]
    assert len(data) == 2
    types = {d["type"] for d in data}
    assert types == {"support", "pressure"}

    for d in data:
        assert client.delete(f"/api/v1/support-resistance/{d['id']}", headers=headers).status_code == 200
    assert client.get("/api/v1/support-resistance", headers=headers).json()["data"] == []


def test_list_filter_by_symbol(client: TestClient, user_token: str):
    headers = _auth(user_token)
    client.post(
        "/api/v1/support-resistance", json={"symbol": "600519", "type": "support", "price": 1200}, headers=headers
    )
    client.post(
        "/api/v1/support-resistance", json={"symbol": "000001", "type": "support", "price": 3000}, headers=headers
    )
    all_rows = client.get("/api/v1/support-resistance", headers=headers).json()["data"]
    assert len(all_rows) == 2


def test_invalid_type_rejected(client: TestClient, user_token: str):
    resp = client.post(
        "/api/v1/support-resistance",
        json={"symbol": "600519", "type": "mid", "price": 1200},
        headers=_auth(user_token),
    )
    assert resp.status_code == 422


def test_unknown_symbol(client: TestClient, user_token: str):
    resp = client.post(
        "/api/v1/support-resistance",
        json={"symbol": "999999", "type": "support", "price": 1200},
        headers=_auth(user_token),
    )
    assert resp.status_code == 400


def test_delete_other_user_isolated(client: TestClient, user_token: str):
    headers_a = _auth(user_token)
    row = client.post(
        "/api/v1/support-resistance",
        json={"symbol": "600519", "type": "support", "price": 1200},
        headers=headers_a,
    ).json()["data"]

    uname = f"{_PREFIX}b{uuid.uuid4().hex[:8]}"
    try:
        token_b = client.post("/api/v1/auth/register", json={"username": uname, "password": "pass123456"}).json()[
            "data"
        ]["token"]
        resp = client.delete(f"/api/v1/support-resistance/{row['id']}", headers=_auth(token_b))
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


def test_requires_token(client: TestClient):
    assert client.get("/api/v1/support-resistance").status_code == 401

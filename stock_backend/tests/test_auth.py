"""2.1 用户鉴权 API 测试：注册/登录/JWT/用户资料更新。"""

import uuid

from app.models.user import User
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_auth_"


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


def _register(client: TestClient, username: str, password: str = "pass123456"):
    return client.post("/api/v1/auth/register", json={"username": username, "password": password})


def test_register_success(client: TestClient):
    uname = _uname()
    try:
        resp = _register(client, uname)
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["token"]
        assert data["user"]["username"] == uname
        assert "password_hash" not in data["user"]
    finally:
        _cleanup_users(uname)


def test_register_duplicate(client: TestClient):
    uname = _uname()
    try:
        assert _register(client, uname).json()["code"] == 0
        resp = _register(client, uname)
        assert resp.status_code == 400
        assert resp.json()["code"] == 40001
    finally:
        _cleanup_users(uname)


def test_register_invalid_username(client: TestClient):
    resp = client.post("/api/v1/auth/register", json={"username": "带空格 名", "password": "pass123456"})
    assert resp.status_code == 422


def test_login_success_and_me(client: TestClient):
    uname = _uname()
    try:
        _register(client, uname)
        resp = client.post("/api/v1/auth/login", json={"username": uname, "password": "pass123456"})
        assert resp.status_code == 200
        token = resp.json()["data"]["token"]
        me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["data"]["username"] == uname
    finally:
        _cleanup_users(uname)


def test_login_wrong_password(client: TestClient):
    uname = _uname()
    try:
        _register(client, uname)
        resp = client.post("/api/v1/auth/login", json={"username": uname, "password": "wrongpass1"})
        assert resp.status_code == 401
    finally:
        _cleanup_users(uname)


def test_me_requires_token(client: TestClient):
    assert client.get("/api/v1/users/me").status_code == 401
    assert client.get("/api/v1/users/me", headers={"Authorization": "Bearer bad.token.here"}).status_code == 401


def test_update_me(client: TestClient):
    uname = _uname()
    try:
        token = _register(client, uname).json()["data"]["token"]
        resp = client.put(
            "/api/v1/users/me", json={"nickname": "昵称测试"}, headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["nickname"] == "昵称测试"
    finally:
        _cleanup_users(uname)

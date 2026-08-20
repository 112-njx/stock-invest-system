"""V0.2 阶段四 4.3 测试：管理员端点鉴权 + Provider 健康检查。"""

import uuid

import pytest
from app.models.user import User
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_admin_"


@pytest.fixture()
def admin_token(client: TestClient) -> str:
    uname = f"{_PREFIX}{uuid.uuid4().hex[:8]}"
    try:
        resp = client.post("/api/v1/auth/register", json={"username": uname, "password": "pass123456"})
        token = resp.json()["data"]["token"]
        db = get_session()
        try:
            u = db.query(User).filter(User.username == uname).first()
            u.is_admin = True
            db.commit()
        finally:
            db.close()
        yield token
    finally:
        db = get_session()
        try:
            u = db.query(User).filter(User.username == uname).first()
            if u:
                db.delete(u)
            db.commit()
        finally:
            db.close()


@pytest.fixture()
def normal_token(client: TestClient) -> str:
    uname = f"{_PREFIX}n{uuid.uuid4().hex[:8]}"
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


def test_providers_health_requires_token(client: TestClient):
    assert client.get("/api/v1/admin/providers/health").status_code == 401


def test_providers_health_rejects_non_admin(client: TestClient, normal_token: str):
    resp = client.get("/api/v1/admin/providers/health", headers=_auth(normal_token))
    assert resp.status_code == 403


def test_providers_health_returns_statuses(client: TestClient, admin_token: str):
    resp = client.get("/api/v1/admin/providers/health", headers=_auth(admin_token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data, "至少有一个 Provider"
    names = {p["name"] for p in data}
    assert "eastmoney" in names  # 默认优先级链含东方财富
    for p in data:
        assert p["state"] in ("closed", "open", "half_open")
        assert "failures" in p and "last_success_at" in p

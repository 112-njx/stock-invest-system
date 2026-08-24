"""阶段八 8.5 策略模板库测试。"""

import uuid

from app.agent.strategy_validator import validate_strategy
from app.models.user import User
from app.repositories import strategy_repo
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_tpl_"


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _register(client: TestClient, username: str) -> str:
    r = client.post("/api/v1/auth/register", json={"username": username, "password": "pass123456"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _cleanup_users(*unames: str) -> None:
    db = get_session()
    try:
        for u in unames:
            row = db.query(User).filter(User.username == u).first()
            if row:
                db.delete(row)
        db.commit()
    finally:
        db.close()


def test_five_templates_seeded_and_valid():
    """5 个内置模板存在且全部通过三级校验。"""
    db = get_session()
    try:
        templates = strategy_repo.list_templates(db)
        assert len(templates) == 5
        names = [t.name for t in templates]
        assert names == ["双均线交叉", "MACD金叉死叉", "KDJ超买超卖", "布林带突破", "成交量异动"]
        for t in templates:
            result = validate_strategy(t.code)
            assert result["valid"] is True, f"{t.name} 校验失败: {result['errors']}"
    finally:
        db.close()


def test_list_templates_without_code(client: TestClient):
    uname = _uname()
    try:
        token = _register(client, uname)
        resp = client.get("/api/v1/strategy-templates", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 5
        # 列表不含完整 code
        assert all("code" not in t for t in data)
        assert all("name" in t and "description" in t and "params_schema" in t for t in data)
    finally:
        _cleanup_users(uname)


def test_get_template_detail_with_code(client: TestClient):
    uname = _uname()
    try:
        token = _register(client, uname)
        db = get_session()
        try:
            tid = strategy_repo.list_templates(db)[0].id
        finally:
            db.close()
        detail = client.get(f"/api/v1/strategy-templates/{tid}", headers=_auth(token)).json()["data"]
        assert "code" in detail and "def on_bar" in detail["code"]

        # 不存在 → 404
        assert client.get("/api/v1/strategy-templates/999999", headers=_auth(token)).status_code == 404
    finally:
        _cleanup_users(uname)


def test_templates_require_auth(client: TestClient):
    assert client.get("/api/v1/strategy-templates").status_code == 401
    assert client.get("/api/v1/strategy-templates/1").status_code == 401

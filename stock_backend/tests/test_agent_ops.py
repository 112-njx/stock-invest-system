"""5.5 补齐接口测试：GET /agent/runs、/agent/runs/{id}、/memory/files。"""

import uuid

from app.models.user import User
from app.repositories import agent_repo
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_aops_"


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _register(client: TestClient, username: str) -> dict:
    r = client.post("/api/v1/auth/register", json={"username": username, "password": "pass123456"})
    assert r.status_code == 200, r.text
    return r.json()["data"]


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


def test_agent_runs_list_and_detail(client: TestClient):
    uname = _uname()
    try:
        user = _register(client, uname)
        uid = user["user"]["id"]
        h = _auth(user["token"])

        # 初始空列表
        assert client.get("/api/v1/agent/runs", headers=h).json()["data"] == []

        # 造一条运行记录 + 步骤
        db = get_session()
        try:
            run = agent_repo.create_run(db, uid, run_type="diagnostic", input_text="分析趋势")
            agent_repo.add_step(db, run.id, "analyst", "analyst", "技术面看多")
            agent_repo.finish_run(db, run, status="success", output="结论：持有", tokens=120)
            db.commit()
            run_id = run.id
        finally:
            db.close()

        rows = client.get("/api/v1/agent/runs", headers=h).json()["data"]
        assert any(r["id"] == run_id and r["status"] == "success" for r in rows)

        detail = client.get(f"/api/v1/agent/runs/{run_id}", headers=h).json()["data"]
        assert detail["output"] == "结论：持有"
        assert detail["tokens"] == 120
        assert len(detail["steps"]) == 1
        assert detail["steps"][0]["step_name"] == "analyst"
    finally:
        _cleanup_users(uname)


def test_agent_runs_ownership_and_auth(client: TestClient):
    uname1, uname2 = _uname(), _uname()
    try:
        u1 = _register(client, uname1)
        u2 = _register(client, uname2)
        db = get_session()
        try:
            run = agent_repo.create_run(db, u1["user"]["id"], run_type="custom", input_text="x")
            db.commit()
            run_id = run.id
        finally:
            db.close()

        # 越权访问他人运行记录 404
        assert client.get(f"/api/v1/agent/runs/{run_id}", headers=_auth(u2["token"])).status_code == 404
        # 未登录 401
        assert client.get("/api/v1/agent/runs").status_code == 401
        assert client.get("/api/v1/memory/files").status_code == 401
    finally:
        _cleanup_users(uname1, uname2)


def test_memory_files_list(client: TestClient):
    uname = _uname()
    try:
        user = _register(client, uname)
        uid = user["user"]["id"]
        h = _auth(user["token"])

        db = get_session()
        try:
            agent_repo.upsert_memory_file(db, uid, f"data/memory/{uid}/rule.md", "rule")
            db.commit()
        finally:
            db.close()

        rows = client.get("/api/v1/memory/files", headers=h).json()["data"]
        assert any(f["path"].endswith("rule.md") and f["content_type"] == "rule" for f in rows)
    finally:
        _cleanup_users(uname)


def test_memory_facts_list_filter_delete_clear(client: TestClient):
    uname = _uname()
    try:
        user = _register(client, uname)
        uid = user["user"]["id"]
        h = _auth(user["token"])

        db = get_session()
        try:
            c1 = agent_repo.add_memory_chunk(db, uid, "rule", 1, "止损不超过2%", "v1", None, importance=8)
            agent_repo.add_memory_chunk(db, uid, "preference", 1, "偏好短线", "v2", None, importance=3)
            db.commit()
            c1_id = c1.id
        finally:
            db.close()

        # 列表
        data = client.get("/api/v1/memory/facts", headers=h).json()["data"]
        assert data["total"] == 2
        assert any(i["id"] == c1_id and i["importance"] == 8 and i["source_id"] == 1 for i in data["items"])

        # 按重要性筛选
        data = client.get("/api/v1/memory/facts?importance_min=7", headers=h).json()["data"]
        assert data["total"] == 1 and data["items"][0]["id"] == c1_id

        # 删除单条
        assert client.delete(f"/api/v1/memory/facts/{c1_id}", headers=h).status_code == 200
        assert client.get("/api/v1/memory/facts", headers=h).json()["data"]["total"] == 1

        # 越权：删除他人记忆 404（用 c2 已删则再造，此处直接验证不存在 id）
        assert client.delete("/api/v1/memory/facts/999999", headers=h).status_code == 404

        # 清空
        assert client.delete("/api/v1/memory/facts", headers=h).status_code == 200
        assert client.get("/api/v1/memory/facts", headers=h).json()["data"]["total"] == 0
    finally:
        _cleanup_users(uname)


def test_memory_facts_requires_auth(client: TestClient):
    assert client.get("/api/v1/memory/facts").status_code == 401
    assert client.delete("/api/v1/memory/facts").status_code == 401
    assert client.delete("/api/v1/memory/facts/1").status_code == 401

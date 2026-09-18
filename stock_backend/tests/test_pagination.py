"""P1-6a（G09）列表分页 + 消息游标分页测试。

覆盖：
- 5 个列表端点统一信封 `{items,total,page,size,total_pages}`（含 /agent/runs 补齐 total_pages）
- 消息游标分页 `{items,has_more,next_cursor}`：默认 50 条、before 往前翻、翻到最早收尾
- 边界：page/size 越界 422、游标无效 400、未登录 401
"""

import uuid

from app.models.symbol import Symbol
from app.models.user import User
from app.repositories import backtest_repo
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_page_"


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _register(client: TestClient, username: str) -> str:
    r = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "pass123456", "email": f"{username}@test.local"},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


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


def _seed_symbol(code: str) -> int:
    db = get_session()
    try:
        sym = Symbol(code=code, name="分页测试标的", type="stock", market="SSE")
        db.add(sym)
        db.commit()
        db.refresh(sym)
        return sym.id
    finally:
        db.close()


def _cleanup_symbol(code: str) -> None:
    db = get_session()
    try:
        sym = db.query(Symbol).filter(Symbol.code == code).first()
        if sym:
            db.delete(sym)
        db.commit()
    finally:
        db.close()


def _envelope_shape_ok(data: dict) -> bool:
    return set(data) == {"items", "total", "page", "size", "total_pages"}


# ---- 列表端点统一分页信封 ----
def test_conversations_pagination_envelope(client: TestClient):
    uname = _uname()
    try:
        h = _auth(_register(client, uname))
        for i in range(3):
            assert client.post("/api/v1/conversations", json={"title": f"会话{i}"}, headers=h).status_code == 200

        data = client.get("/api/v1/conversations?page=1&size=2", headers=h).json()["data"]
        assert _envelope_shape_ok(data), data.keys()
        assert data["page"] == 1 and data["size"] == 2
        assert data["total"] == 3
        assert data["total_pages"] == 2
        assert len(data["items"]) == 2

        # 第二页与第一页不重叠，且只剩 1 条
        page2 = client.get("/api/v1/conversations?page=2&size=2", headers=h).json()["data"]
        assert page2["total"] == 3 and page2["total_pages"] == 2
        assert len(page2["items"]) == 1
        assert {c["id"] for c in data["items"]} & {c["id"] for c in page2["items"]} == set()

        # 超出末页 → 空 items，total 不变
        page9 = client.get("/api/v1/conversations?page=9&size=2", headers=h).json()["data"]
        assert page9["items"] == [] and page9["total"] == 3

        # 默认 size=20
        default = client.get("/api/v1/conversations", headers=h).json()["data"]
        assert default["page"] == 1 and default["size"] == 20
    finally:
        _cleanup_users(uname)


def test_conversations_pagination_invalid_params(client: TestClient):
    uname = _uname()
    try:
        h = _auth(_register(client, uname))
        # size 上限 100
        assert client.get("/api/v1/conversations?size=101", headers=h).status_code == 422
        assert client.get("/api/v1/conversations?size=0", headers=h).status_code == 422
        assert client.get("/api/v1/conversations?page=0", headers=h).status_code == 422
        # 上限内正常
        assert client.get("/api/v1/conversations?size=100", headers=h).status_code == 200
    finally:
        _cleanup_users(uname)


def test_strategies_pagination_envelope(client: TestClient):
    uname = _uname()
    try:
        h = _auth(_register(client, uname))
        for i in range(3):
            r = client.post("/api/v1/strategies", json={"title": f"策略{i}"}, headers=h)
            assert r.status_code == 200, r.text

        data = client.get("/api/v1/strategies?page=1&size=2", headers=h).json()["data"]
        assert _envelope_shape_ok(data)
        assert data["total"] == 3 and data["total_pages"] == 2 and len(data["items"]) == 2
        page2 = client.get("/api/v1/strategies?page=2&size=2", headers=h).json()["data"]
        assert len(page2["items"]) == 1
        assert {s["id"] for s in data["items"]} & {s["id"] for s in page2["items"]} == set()
    finally:
        _cleanup_users(uname)


def test_agents_pagination_envelope(client: TestClient):
    uname = _uname()
    try:
        h = _auth(_register(client, uname))
        for i in range(3):
            r = client.post("/api/v1/agents", json={"name": f"Agent{i}"}, headers=h)
            assert r.status_code == 200, r.text

        data = client.get("/api/v1/agents?page=1&size=2", headers=h).json()["data"]
        assert _envelope_shape_ok(data)
        assert data["total"] == 3 and data["total_pages"] == 2 and len(data["items"]) == 2
        page2 = client.get("/api/v1/agents?page=2&size=2", headers=h).json()["data"]
        assert len(page2["items"]) == 1
        assert {a["id"] for a in data["items"]} & {a["id"] for a in page2["items"]} == set()
    finally:
        _cleanup_users(uname)


def test_backtest_tasks_pagination_envelope(client: TestClient):
    uname = _uname()
    code = "600701"
    try:
        h = _auth(_register(client, uname))
        sid = client.post("/api/v1/strategies", json={"title": "回测分页策略"}, headers=h).json()["data"]["id"]
        symbol_id = _seed_symbol(code)
        db = get_session()
        try:
            for _ in range(3):
                backtest_repo.create_task(db, sid, symbol_id)
            db.commit()
        finally:
            db.close()

        data = client.get(f"/api/v1/backtest/tasks?strategy_id={sid}&page=1&size=2", headers=h).json()["data"]
        assert _envelope_shape_ok(data)
        assert data["total"] == 3 and data["total_pages"] == 2 and len(data["items"]) == 2
        page2 = client.get(f"/api/v1/backtest/tasks?strategy_id={sid}&page=2&size=2", headers=h).json()["data"]
        assert len(page2["items"]) == 1

        # 不带 strategy_id（当前用户全部策略）同样分页
        allp = client.get("/api/v1/backtest/tasks?page=1&size=1", headers=h).json()["data"]
        assert _envelope_shape_ok(allp) and allp["total"] == 3 and len(allp["items"]) == 1
    finally:
        _cleanup_users(uname)
        _cleanup_symbol(code)


def test_agent_runs_envelope_has_total_pages(client: TestClient):
    uname = _uname()
    try:
        h = _auth(_register(client, uname))
        data = client.get("/api/v1/agent/runs", headers=h).json()["data"]
        assert _envelope_shape_ok(data)
        assert data["items"] == [] and data["total"] == 0 and data["total_pages"] == 0
    finally:
        _cleanup_users(uname)


# ---- 消息游标分页 ----
def _seed_messages(client: TestClient, h: dict, conv_id: int, count: int) -> list[int]:
    ids = []
    for i in range(count):
        r = client.post(
            f"/api/v1/conversations/{conv_id}/messages",
            json={"role": "user", "content": f"消息{i}"},
            headers=h,
        )
        assert r.status_code == 200, r.text
        ids.append(r.json()["data"]["id"])
    return ids


def test_messages_cursor_pagination(client: TestClient):
    uname = _uname()
    try:
        h = _auth(_register(client, uname))
        conv_id = client.post("/api/v1/conversations", json={}, headers=h).json()["data"]["id"]
        ids = _seed_messages(client, h, conv_id, 5)

        # 第一页：最新 2 条，升序返回，has_more=True，游标为本页最旧一条
        p1 = client.get(f"/api/v1/conversations/{conv_id}/messages?limit=2", headers=h).json()["data"]
        assert set(p1) == {"items", "has_more", "next_cursor"}
        assert [m["id"] for m in p1["items"]] == [ids[3], ids[4]]  # 时间升序
        assert p1["has_more"] is True
        assert p1["next_cursor"] == ids[3]

        # 第二页：用游标往前取，仍为升序
        p2 = client.get(
            f"/api/v1/conversations/{conv_id}/messages?limit=2&before={p1['next_cursor']}", headers=h
        ).json()["data"]
        assert [m["id"] for m in p2["items"]] == [ids[1], ids[2]]
        assert p2["has_more"] is True and p2["next_cursor"] == ids[1]

        # 第三页：只剩 1 条，has_more=False，next_cursor 归 null
        p3 = client.get(
            f"/api/v1/conversations/{conv_id}/messages?limit=2&before={p2['next_cursor']}", headers=h
        ).json()["data"]
        assert [m["id"] for m in p3["items"]] == [ids[0]]
        assert p3["has_more"] is False and p3["next_cursor"] is None

        # 三页拼接 == 全量且不重不漏
        collected = [m["id"] for m in p1["items"] + p2["items"] + p3["items"]]
        assert sorted(collected) == sorted(ids) and len(collected) == 5
    finally:
        _cleanup_users(uname)


def test_messages_default_limit_is_50(client: TestClient):
    uname = _uname()
    try:
        h = _auth(_register(client, uname))
        conv_id = client.post("/api/v1/conversations", json={}, headers=h).json()["data"]["id"]
        ids = _seed_messages(client, h, conv_id, 55)

        data = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=h).json()["data"]
        assert len(data["items"]) == 50
        assert data["has_more"] is True
        # 默认取最新 50 条（升序 → 最后一条是最新的）
        assert data["items"][-1]["id"] == ids[-1]
        assert data["items"][0]["id"] == ids[5]
    finally:
        _cleanup_users(uname)


def test_messages_empty_conversation(client: TestClient):
    uname = _uname()
    try:
        h = _auth(_register(client, uname))
        conv_id = client.post("/api/v1/conversations", json={}, headers=h).json()["data"]["id"]
        data = client.get(f"/api/v1/conversations/{conv_id}/messages", headers=h).json()["data"]
        assert data["items"] == [] and data["has_more"] is False and data["next_cursor"] is None
    finally:
        _cleanup_users(uname)


def test_messages_invalid_cursor_rejected(client: TestClient):
    """游标必须属于本会话：跨会话游标 → 400，不存在的 id → 400。"""
    uname = _uname()
    try:
        h = _auth(_register(client, uname))
        c1 = client.post("/api/v1/conversations", json={}, headers=h).json()["data"]["id"]
        c2 = client.post("/api/v1/conversations", json={}, headers=h).json()["data"]["id"]
        other_ids = _seed_messages(client, h, c2, 1)

        r = client.get(f"/api/v1/conversations/{c1}/messages?before={other_ids[0]}", headers=h)
        assert r.status_code == 400
        assert r.json()["code"] == 40005

        r = client.get(f"/api/v1/conversations/{c1}/messages?before=999999999", headers=h)
        assert r.status_code == 400

        # limit 越界 422
        assert client.get(f"/api/v1/conversations/{c1}/messages?limit=0", headers=h).status_code == 422
        assert client.get(f"/api/v1/conversations/{c1}/messages?limit=201", headers=h).status_code == 422
    finally:
        _cleanup_users(uname)


def test_pagination_endpoints_require_token(client: TestClient):
    assert client.get("/api/v1/conversations").status_code == 401
    assert client.get("/api/v1/strategies").status_code == 401
    assert client.get("/api/v1/agents").status_code == 401
    assert client.get("/api/v1/agent/runs").status_code == 401
    assert client.get("/api/v1/backtest/tasks").status_code == 401
    assert client.get("/api/v1/conversations/1/messages").status_code == 401

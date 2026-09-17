"""G30 安全测试：用户数据隔离（横向越权）+ 用户输入校验。

说明：XSS 的**渲染侧**消毒由前端 scripts/verify-xss.mjs 验证（DOMPurify + escape-first）；
本文件验证**服务端**侧：越权访问一律 404、非法输入一律 422。
"""

import uuid

from app.models.user import User
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_g30_"


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _register(client: TestClient, uname: str) -> str:
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": uname, "password": "pass123456", "email": f"{uname}@test.local"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _cleanup(*usernames: str) -> None:
    db = get_session()
    try:
        for uname in usernames:
            u = db.query(User).filter(User.username == uname).first()
            if u:
                db.delete(u)
            db.commit()
    finally:
        db.close()


# ==================== 横向越权（用户 A 不得访问 B 的数据）====================


def test_chat_rejects_other_users_conversation(client: TestClient):
    """A 用 B 的 conversation_id 发消息 → 404（不得写入他人会话）。"""
    ua, ub = _uname(), _uname()
    try:
        ta, tb = _register(client, ua), _register(client, ub)
        # B 建会话
        conv_b = client.post("/api/v1/conversations", json={"title": "B的会话"}, headers=_auth(tb))
        assert conv_b.status_code == 200
        cid = conv_b.json()["data"]["id"]

        # A 尝试往 B 的会话发消息
        resp = client.post(
            "/api/v1/conversations/%d/messages" % cid,
            json={"role": "user", "content": "越权写入"},
            headers=_auth(ta),
        )
        assert resp.status_code == 404

        # A 尝试读 B 的会话消息
        assert client.get(f"/api/v1/conversations/{cid}/messages", headers=_auth(ta)).status_code == 404
        # A 尝试删除 B 的会话
        assert client.delete(f"/api/v1/conversations/{cid}", headers=_auth(ta)).status_code == 404
        # A 尝试重命名 B 的会话
        assert (
            client.patch(
                f"/api/v1/conversations/{cid}", json={"title": "改名"}, headers=_auth(ta)
            ).status_code
            == 404
        )
    finally:
        _cleanup(ua, ub)


def test_agent_run_and_steps_isolated(client: TestClient):
    """A 不得读取 B 的 agent run 及其 steps → 404。"""
    ua, ub = _uname(), _uname()
    try:
        ta, tb = _register(client, ua), _register(client, ub)
        # B 建会话（agent_runs 需要 conversation 或独立存在，用会话驱动最简单）
        conv_b = client.post("/api/v1/conversations", json={"title": "B"}, headers=_auth(tb))
        cid = conv_b.json()["data"]["id"]

        # 直接落一条 B 的 agent_run（走 DB，避免依赖 LLM）
        from app.models.agent import AgentRun

        db = get_session()
        try:
            b_user = db.query(User).filter(User.username == ub).first()
            run = AgentRun(user_id=b_user.id, conversation_id=cid, run_type="diagnostic", status="success")
            db.add(run)
            db.commit()
            db.refresh(run)
            run_id = run.id
        finally:
            db.close()

        # A 读 B 的 run / steps → 404
        assert client.get(f"/api/v1/agent/runs/{run_id}", headers=_auth(ta)).status_code == 404
        assert client.get(f"/api/v1/agent/runs/{run_id}/steps", headers=_auth(ta)).status_code == 404
        # B 自己能读
        assert client.get(f"/api/v1/agent/runs/{run_id}", headers=_auth(tb)).status_code == 200
    finally:
        _cleanup(ua, ub)


def test_memory_facts_isolated(client: TestClient):
    """A 不得删除 B 的记忆事实 → 404；A 的 facts 列表不含 B 的数据。"""
    ua, ub = _uname(), _uname()
    try:
        ta, tb = _register(client, ua), _register(client, ub)

        from app.models.agent import MemoryChunk

        db = get_session()
        try:
            b_user = db.query(User).filter(User.username == ub).first()
            chunk = MemoryChunk(
                user_id=b_user.id,
                source_type="rule",
                content="B的私密交易规则",
                vector_id=f"g30_{uuid.uuid4().hex[:12]}",
                importance=8,
            )
            db.add(chunk)
            db.commit()
            db.refresh(chunk)
            fact_id = chunk.id
        finally:
            db.close()

        # A 删 B 的 fact → 404
        assert client.delete(f"/api/v1/memory/facts/{fact_id}", headers=_auth(ta)).status_code == 404
        # B 自己删 → 200
        assert client.delete(f"/api/v1/memory/facts/{fact_id}", headers=_auth(tb)).status_code == 200

        # A 的列表里不应出现 B 的内容
        facts_a = client.get("/api/v1/memory/facts", headers=_auth(ta)).json()["data"]
        items = facts_a["items"] if isinstance(facts_a, dict) else facts_a
        assert all("B的私密交易规则" not in (f.get("content") or "") for f in items)
    finally:
        _cleanup(ua, ub)


def test_memory_files_isolated(client: TestClient):
    """A 不得看到 B 的记忆文件。"""
    ua, ub = _uname(), _uname()
    try:
        ta, tb = _register(client, ua), _register(client, ub)

        from app.models.user import UserMemoryFile

        db = get_session()
        try:
            b_user = db.query(User).filter(User.username == ub).first()
            db.add(
                UserMemoryFile(
                    user_id=b_user.id,
                    file_path=f"g30/{uuid.uuid4().hex[:8]}/rule.md",
                    content_type="rule",
                )
            )
            db.commit()
        finally:
            db.close()

        files_a = client.get("/api/v1/memory/files", headers=_auth(ta)).json()["data"]
        rows = files_a["items"] if isinstance(files_a, dict) else files_a
        assert all("g30/" not in (f.get("file_path") or "") for f in rows)
    finally:
        _cleanup(ua, ub)


def test_backtest_result_isolated(client: TestClient):
    """A 不得读取 B 的策略回测结果 / 任务 → 404。"""
    ua, ub = _uname(), _uname()
    try:
        ta, tb = _register(client, ua), _register(client, ub)
        # B 建策略
        s = client.post(
            "/api/v1/strategies",
            json={"title": "B策略", "code": "def initialize(ctx):\n    pass\n"},
            headers=_auth(tb),
        )
        assert s.status_code == 200, s.text
        sid = s.json()["data"]["id"]

        # A 用 B 的 strategy_id 发起回测 → 404
        resp = client.post(
            "/api/v1/backtest",
            json={"strategy_id": sid, "symbol": "600519"},
            headers=_auth(ta),
        )
        assert resp.status_code == 404
        # A 读 B 策略的回测结果 → 404
        assert client.get(f"/api/v1/backtest/results?strategy_id={sid}", headers=_auth(ta)).status_code == 404
    finally:
        _cleanup(ua, ub)


def test_strategy_and_watchlist_isolated(client: TestClient):
    """A 不得读写 B 的策略 / 关注列表。"""
    ua, ub = _uname(), _uname()
    try:
        ta, tb = _register(client, ua), _register(client, ub)
        s = client.post("/api/v1/strategies", json={"title": "B策略2"}, headers=_auth(tb))
        sid = s.json()["data"]["id"]

        assert client.get(f"/api/v1/strategies/{sid}", headers=_auth(ta)).status_code == 404
        assert (
            client.put(f"/api/v1/strategies/{sid}", json={"title": "篡改"}, headers=_auth(ta)).status_code
            == 404
        )
        assert client.delete(f"/api/v1/strategies/{sid}", headers=_auth(ta)).status_code == 404

        wl_b = client.post("/api/v1/watchlist", json={"symbol": "600519"}, headers=_auth(tb))
        if wl_b.status_code == 200:
            wid = wl_b.json()["data"]["id"]
            assert client.delete(f"/api/v1/watchlist/{wid}", headers=_auth(ta)).status_code == 404
        # A 的关注列表不含 B 添加的
        wl_a = client.get("/api/v1/watchlist", headers=_auth(ta)).json()["data"]
        assert wl_a == [] or all(r.get("code") != "600519" for r in wl_a)
    finally:
        _cleanup(ua, ub)


# ==================== 输入校验（G30）====================


def test_nickname_rejects_control_chars(client: TestClient):
    """昵称含控制字符 → 422。"""
    ua = _uname()
    try:
        ta = _register(client, ua)
        resp = client.put("/api/v1/users/me", json={"nickname": "正常\x00注入"}, headers=_auth(ta))
        assert resp.status_code == 422
        # 制表/换行放行（多行文本合法）
        assert client.put("/api/v1/users/me", json={"nickname": "正常\n昵称"}, headers=_auth(ta)).status_code == 200
    finally:
        _cleanup(ua)


def test_nickname_length_capped(client: TestClient):
    ua = _uname()
    try:
        ta = _register(client, ua)
        assert client.put("/api/v1/users/me", json={"nickname": "x" * 65}, headers=_auth(ta)).status_code == 422
    finally:
        _cleanup(ua)


def test_avatar_url_rejects_javascript_scheme(client: TestClient):
    """头像地址禁 javascript:/data: 等可执行协议 → 422。"""
    ua = _uname()
    try:
        ta = _register(client, ua)
        for bad in ["javascript:alert(1)", "data:text/html,<script>alert(1)</script>", "vbscript:x"]:
            resp = client.put("/api/v1/users/me", json={"avatar_url": bad}, headers=_auth(ta))
            assert resp.status_code == 422, f"{bad} 应被拒绝"
        # http(s) 与站内路径放行
        assert (
            client.put("/api/v1/users/me", json={"avatar_url": "https://cdn.example.com/a.png"}, headers=_auth(ta)).status_code
            == 200
        )
        assert client.put("/api/v1/users/me", json={"avatar_url": "/static/a.png"}, headers=_auth(ta)).status_code == 200
    finally:
        _cleanup(ua)


def test_agent_system_prompt_requires_length_limit(client: TestClient):
    """system_prompt 超长 → 422；含控制字符 → 422；正常内容可存。"""
    ua = _uname()
    try:
        ta = _register(client, ua)
        base = {"name": "G30测试Agent", "agent_type": "custom"}
        assert (
            client.post("/api/v1/agents", json={**base, "system_prompt": "x" * 8001}, headers=_auth(ta)).status_code
            == 422
        )
        assert (
            client.post("/api/v1/agents", json={**base, "system_prompt": "提示\x01注入"}, headers=_auth(ta)).status_code
            == 422
        )
        ok = client.post(
            "/api/v1/agents",
            json={**base, "system_prompt": "你是一名量化分析师。\n关注风险。"},
            headers=_auth(ta),
        )
        assert ok.status_code == 200, ok.text
    finally:
        _cleanup(ua)


def test_strategy_title_and_code_limits(client: TestClient):
    """策略标题/描述/代码超长 → 422；控制字符 → 422。"""
    ua = _uname()
    try:
        ta = _register(client, ua)
        assert client.post("/api/v1/strategies", json={"title": "x" * 129}, headers=_auth(ta)).status_code == 422
        assert client.post("/api/v1/strategies", json={"title": "标题\x00"}, headers=_auth(ta)).status_code == 422
        assert (
            client.post(
                "/api/v1/strategies", json={"title": "正常", "description": "d" * 2001}, headers=_auth(ta)
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/api/v1/strategies", json={"title": "正常", "code": "c" * 20001}, headers=_auth(ta)
            ).status_code
            == 422
        )
    finally:
        _cleanup(ua)


def test_chat_content_length_and_control_chars(client: TestClient):
    """聊天输入超长 / 含控制字符 → 422；run_type 非枚举 → 422。"""
    ua = _uname()
    try:
        ta = _register(client, ua)
        assert client.post("/api/v1/chat", json={"content": "x" * 20001}, headers=_auth(ta)).status_code == 422
        assert client.post("/api/v1/chat", json={"content": "hi\x00"}, headers=_auth(ta)).status_code == 422
        assert (
            client.post("/api/v1/chat", json={"content": "hi", "run_type": "任意值"}, headers=_auth(ta)).status_code
            == 422
        )
    finally:
        _cleanup(ua)


def test_xss_payload_stored_verbatim_and_returned_as_text(client: TestClient):
    """XSS payload 作为纯文本存取（服务端不做 HTML 转义，渲染侧由前端消毒）。

    断言：含 payload 的标题能正常保存与读回，且响应体是 JSON 文本字段
    （不会被服务端误当作 HTML 渲染），渲染安全由 scripts/verify-xss.mjs 覆盖。
    """
    ua = _uname()
    payload = '<img src=x onerror=alert(1)>'
    try:
        ta = _register(client, ua)
        resp = client.post("/api/v1/strategies", json={"title": payload}, headers=_auth(ta))
        assert resp.status_code == 200, resp.text
        sid = resp.json()["data"]["id"]
        got = client.get(f"/api/v1/strategies/{sid}", headers=_auth(ta))
        assert got.status_code == 200
        assert got.json()["data"]["title"] == payload  # 原样存回，未损坏
        # 响应 Content-Type 必须是 JSON（浏览器不会把 JSON 当 HTML 执行）
        assert "application/json" in got.headers.get("content-type", "")
    finally:
        _cleanup(ua)

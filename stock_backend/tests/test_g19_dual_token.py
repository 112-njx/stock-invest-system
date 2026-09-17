"""G19 双 token + 会话管理测试。

必测：登录/登出/refresh 全流程、refresh 轮换与复用检测、access 过期与黑名单、
踢出设备、横向越权（403/404）。
"""

import uuid

from app.core.security import (
    create_access_token,
    decode_access_token,
    decode_access_token_full,
    is_access_token_blacklisted,
)
from app.models.session import UserSession
from app.models.user import User
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_g19_"


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


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


def _register_and_login(client: TestClient, uname: str | None = None):
    """注册并登录，返回 (token, refresh_cookie, username)。"""
    uname = uname or _uname()
    email = f"{uname}@test.local"
    client.post("/api/v1/auth/register", json={"username": uname, "password": "pass123456", "email": email})
    resp = client.post("/api/v1/auth/login", json={"username": uname, "password": "pass123456"})
    assert resp.status_code == 200, f"login failed: {resp.json()}"
    data = resp.json()["data"]
    token = data["token"]
    # 从 Set-Cookie 中提取 refresh token
    cookies = resp.cookies
    refresh = cookies.get("refresh_token")
    return token, refresh, uname


# ---------- Access Token JWT 结构 ----------


def test_access_token_contains_jti_and_iat():
    """G19 access token 必须包含 jti（唯一ID）和 iat（签发时间）。"""
    token = create_access_token(1)
    payload = decode_access_token_full(token)
    assert payload is not None
    assert "jti" in payload
    assert "iat" in payload
    assert payload["sub"] == "1"


def test_decode_access_token_backward_compatible():
    """向后兼容：旧 decode_access_token 仍返回 user_id。"""
    token = create_access_token(42)
    assert decode_access_token(token) == 42


# ---------- 登录返回双 token ----------


def test_login_returns_access_token_and_refresh_cookie(client: TestClient):
    """登录响应：access token 在 JSON body，refresh token 在 HttpOnly Cookie。"""
    uname = _uname()
    try:
        client.post("/api/v1/auth/register", json={"username": uname, "password": "pass123456", "email": f"{uname}@test.local"})
        resp = client.post("/api/v1/auth/login", json={"username": uname, "password": "pass123456"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        # access token 在 body
        assert "token" in data
        assert data["user"]["username"] == uname
        # refresh token 在 Cookie
        assert "refresh_token" in resp.cookies
        # Cookie 应有 HttpOnly 属性
        cookie_header = resp.headers.get("set-cookie", "")
        assert "httponly" in cookie_header.lower()
    finally:
        _cleanup(uname)


def test_register_also_creates_session(client: TestClient):
    """注册也创建 session（双 token）。"""
    uname = _uname()
    try:
        resp = client.post("/api/v1/auth/register", json={"username": uname, "password": "pass123456", "email": f"{uname}@test.local"})
        assert resp.status_code == 200
        assert "refresh_token" in resp.cookies

        # 验证数据库中有 session 记录
        db = get_session()
        try:
            user = db.query(User).filter(User.username == uname).first()
            sessions = db.query(UserSession).filter(UserSession.user_id == user.id).all()
            assert len(sessions) >= 1
            assert sessions[0].revoked_at is None  # 活跃
        finally:
            db.close()
    finally:
        _cleanup(uname)


# ---------- Refresh 轮换 ----------


def test_refresh_rotates_tokens(client: TestClient):
    """刷新：旧 refresh → 新 access + 新 refresh（Cookie 更新）。"""
    uname = _uname()
    try:
        token1, refresh1, _ = _register_and_login(client, uname)

        # 用 refresh1 请求刷新
        client.cookies.set("refresh_token", refresh1)
        resp = client.post("/api/v1/auth/refresh")
        assert resp.status_code == 200
        new_token = resp.json()["data"]["token"]
        assert new_token != token1  # 新 access token

        # 新 refresh token 在 Cookie 中
        new_refresh = resp.cookies.get("refresh_token")
        assert new_refresh is not None
        assert new_refresh != refresh1  # 已轮换

        # 新 access token 可用于认证
        me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {new_token}"})
        assert me.status_code == 200
        assert me.json()["data"]["username"] == uname
    finally:
        _cleanup(uname)


def test_refresh_reuse_detection(client: TestClient):
    """复用检测：同一 refresh token 用两次 → 所有设备被踢。"""
    uname = _uname()
    try:
        _, refresh1, _ = _register_and_login(client, uname)

        # 第一次刷新（正常）
        client.cookies.set("refresh_token", refresh1)
        resp1 = client.post("/api/v1/auth/refresh")
        assert resp1.status_code == 200

        # 第二次用同一个 refresh token（复用攻击！）
        client.cookies.set("refresh_token", refresh1)
        resp2 = client.post("/api/v1/auth/refresh")
        assert resp2.status_code == 401  # 复用检测触发

        # 所有 session 应被吊销
        db = get_session()
        try:
            user = db.query(User).filter(User.username == uname).first()
            active = (
                db.query(UserSession)
                .filter(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
                .all()
            )
            assert len(active) == 0, "复用检测后所有 session 应被吊销"
        finally:
            db.close()
    finally:
        _cleanup(uname)


# ---------- 登出 ----------


def test_logout_invalidates_tokens(client: TestClient):
    """登出后 access token 入黑名单，refresh session 吊销。"""
    uname = _uname()
    try:
        token, refresh, _ = _register_and_login(client, uname)

        # 登出
        client.cookies.set("refresh_token", refresh)
        resp = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

        # access token 应在黑名单中
        payload = decode_access_token_full(token)
        if payload and payload.get("jti"):
            assert is_access_token_blacklisted(payload["jti"])

        # 用已登出的 access token 访问应返回 401
        me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 401
    finally:
        _cleanup(uname)


# ---------- 会话管理 ----------


def test_sessions_list_with_current_marker(client: TestClient):
    """GET /auth/sessions 返回活跃设备列表，标记当前设备。"""
    uname = _uname()
    try:
        _, refresh, _ = _register_and_login(client, uname)
        token2, _, _ = _register_and_login(client, uname)  # 再登录一次（第二个 session）

        # 用第一个 refresh cookie 查询
        client.cookies.set("refresh_token", refresh)
        # 需要 access token 来认证
        token1_resp = client.post("/api/v1/auth/login", json={"username": uname, "password": "pass123456"})
        token1 = token1_resp.json()["data"]["token"]

        resp = client.get("/api/v1/auth/sessions", headers={"Authorization": f"Bearer {token1}"})
        assert resp.status_code == 200
        sessions = resp.json()["data"]
        assert len(sessions) >= 2  # 至少两个 session

        # 至少一个标记为当前
        current_sessions = [s for s in sessions if s["is_current"]]
        assert len(current_sessions) >= 1
    finally:
        _cleanup(uname)


def test_revoke_session_kicks_device(client: TestClient):
    """DELETE /auth/sessions/{id} 踢出设备后，该设备 refresh 失效。"""
    uname = _uname()
    try:
        token, refresh, _ = _register_and_login(client, uname)

        # 获取 sessions
        resp = client.get("/api/v1/auth/sessions", headers={"Authorization": f"Bearer {token}"})
        sessions = resp.json()["data"]
        assert len(sessions) >= 1

        # 踢出第一个 session
        session_id = sessions[0]["id"]
        revoke_resp = client.delete(
            f"/api/v1/auth/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert revoke_resp.status_code == 200

        # session 应已吊销
        db = get_session()
        try:
            s = db.query(UserSession).filter(UserSession.id == session_id).first()
            assert s.revoked_at is not None
        finally:
            db.close()
    finally:
        _cleanup(uname)


def test_revoke_other_users_session_returns_404(client: TestClient):
    """横向越权：用户 A 不能踢出用户 B 的设备（返回 404）。"""
    uname_a = _uname()
    uname_b = _uname()
    try:
        token_a, _, _ = _register_and_login(client, uname_a)
        _, _, _ = _register_and_login(client, uname_b)

        # 获取 B 的 session
        db = get_session()
        try:
            user_b = db.query(User).filter(User.username == uname_b).first()
            b_session = db.query(UserSession).filter(UserSession.user_id == user_b.id).first()
            b_session_id = b_session.id
        finally:
            db.close()

        # A 尝试踢出 B 的设备
        resp = client.delete(
            f"/api/v1/auth/sessions/{b_session_id}",
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert resp.status_code == 404  # 对 A 不可见
    finally:
        _cleanup(uname_a, uname_b)


# ---------- Refresh token 安全 ----------


def test_refresh_without_cookie_returns_401(client: TestClient):
    """无 refresh Cookie 时 /auth/refresh 返回 401。"""
    # 清除所有 cookie
    client.cookies.clear()
    resp = client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401


def test_refresh_with_invalid_cookie_returns_401(client: TestClient):
    """无效 refresh Cookie 返回 401。"""
    client.cookies.set("refresh_token", "invalid-token-abc123")
    resp = client.post("/api/v1/auth/refresh")
    assert resp.status_code == 401


# ---------- 向后兼容 ----------


def test_me_still_works_with_bearer_token(client: TestClient):
    """向后兼容：GET /users/me 仍可用 Bearer token 认证。"""
    uname = _uname()
    try:
        token, _, _ = _register_and_login(client, uname)
        me = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["data"]["username"] == uname
    finally:
        _cleanup(uname)

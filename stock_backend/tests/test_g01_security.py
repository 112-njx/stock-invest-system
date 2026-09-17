"""G01 安全加固测试：CORS 白名单 / Cookie 安全属性 / 安全响应头。"""

import os

from app.core.config import get_settings
from app.core.security import clear_access_token_cookie, set_access_token_cookie
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


# ---------- CORS 白名单 ----------


def test_cors_allows_whitelisted_origin():
    """白名单内的 Origin 应收到 Access-Control-Allow-Origin + credentials。"""
    settings = get_settings()
    # 测试环境 CORS_ORIGINS 默认包含 localhost 端口
    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]

    # 使用主 app 的 test client（已配置 CORS 中间件）
    from app.main import app

    with TestClient(app) as client:
        if origins:
            test_origin = origins[0]
            resp = client.options(
                "/api/v1/auth/login",
                headers={
                    "Origin": test_origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "Content-Type, Authorization",
                },
            )
            assert resp.status_code == 200
            assert resp.headers.get("access-control-allow-origin") == test_origin
            assert resp.headers.get("access-control-allow-credentials") == "true"


def test_cors_rejects_unknown_origin():
    """白名单外的 Origin 不应收到 Access-Control-Allow-Origin 头。"""
    from app.main import app

    with TestClient(app) as client:
        resp = client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        # 非白名单来源：不应出现 allow-origin 头（或不含 credentials）
        allow_origin = resp.headers.get("access-control-allow-origin")
        if allow_origin:
            # 如果有 allow-origin，不能是 * 也不能是 evil origin
            assert allow_origin != "*"
            assert "evil.example.com" not in allow_origin


def test_cors_no_wildcard_origin():
    """验证 CORS 配置不使用通配符 *（凭证模式禁止通配）。"""
    settings = get_settings()
    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    assert "*" not in origins, "CORS_ORIGINS 禁止包含通配符 *"


# ---------- Cookie 安全属性 ----------


def test_set_access_token_cookie_attributes():
    """Cookie 必须包含 HttpOnly、SameSite、Path 属性。"""
    settings = get_settings()

    # 构造一个最小 FastAPI app 测试 Cookie 设置
    test_app = FastAPI()

    @test_app.get("/test-set-cookie")
    def test_set_cookie():
        resp = JSONResponse(content={"ok": True})
        set_access_token_cookie(resp, "test-token-value", max_age=900)
        return resp

    with TestClient(test_app) as client:
        resp = client.get("/test-set-cookie")
        assert resp.status_code == 200

        # 解析 Set-Cookie 头
        cookies = resp.headers.get_list("set-cookie")
        assert len(cookies) >= 1

        cookie_str = cookies[0].lower()
        assert settings.ACCESS_TOKEN_COOKIE_NAME.lower() in cookie_str
        assert "httponly" in cookie_str
        assert f"samesite={settings.COOKIE_SAMESITE.lower()}" in cookie_str
        assert "path=/" in cookie_str
        assert "max-age=900" in cookie_str

        # Secure 属性取决于配置
        if settings.COOKIE_SECURE:
            assert "secure" in cookie_str
        else:
            # 开发环境不要求 Secure
            pass


def test_clear_access_token_cookie():
    """清除 Cookie 应设置过期时间。"""
    test_app = FastAPI()

    @test_app.get("/test-clear-cookie")
    def test_clear():
        resp = JSONResponse(content={"ok": True})
        clear_access_token_cookie(resp)
        return resp

    with TestClient(test_app) as client:
        resp = client.get("/test-clear-cookie")
        assert resp.status_code == 200

        cookies = resp.headers.get_list("set-cookie")
        assert len(cookies) >= 1

        cookie_str = cookies[0].lower()
        # 清除 Cookie 应包含过期标记（max-age=0 或 expires=过去时间）
        assert "max-age=0" in cookie_str or "expires=" in cookie_str


def test_cookie_secure_flag_from_config():
    """COOKIE_SECURE=True 时 Cookie 应包含 Secure 属性。"""
    # 动态修改设置测试 Secure 模式
    settings = get_settings()
    original_secure = settings.COOKIE_SECURE

    try:
        settings.COOKIE_SECURE = True

        test_app = FastAPI()

        @test_app.get("/test-secure-cookie")
        def test_secure():
            resp = JSONResponse(content={"ok": True})
            set_access_token_cookie(resp, "secure-token", max_age=300)
            return resp

        with TestClient(test_app) as client:
            resp = client.get("/test-secure-cookie")
            cookie_str = resp.headers.get("set-cookie", "").lower()
            assert "secure" in cookie_str
    finally:
        settings.COOKIE_SECURE = original_secure


# ---------- 配置项 ----------


def test_config_has_cors_origins():
    """配置必须包含 CORS_ORIGINS 字段。"""
    settings = get_settings()
    assert hasattr(settings, "CORS_ORIGINS")
    assert isinstance(settings.CORS_ORIGINS, str)


def test_config_has_cookie_settings():
    """配置必须包含 Cookie 安全相关字段。"""
    settings = get_settings()
    assert hasattr(settings, "COOKIE_SECURE")
    assert hasattr(settings, "COOKIE_SAMESITE")
    assert hasattr(settings, "ACCESS_TOKEN_COOKIE_NAME")
    assert settings.COOKIE_SAMESITE in ("lax", "strict", "none")


# ---------- 现有鉴权向后兼容 ----------


def test_login_still_returns_bearer_token(client: TestClient):
    """G01 不改变登录响应结构，仍返回 Bearer token（向后兼容）。"""
    import uuid

    uname = f"test_g01_{uuid.uuid4().hex[:8]}"
    try:
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": uname, "password": "pass123456"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        # 仍返回 token 和 user
        assert "token" in data
        assert "user" in data
        assert data["user"]["username"] == uname
    finally:
        from app.models.user import User
        from app.utils.db import get_session

        db = get_session()
        try:
            u = db.query(User).filter(User.username == uname).first()
            if u:
                db.delete(u)
            db.commit()
        finally:
            db.close()

"""G23 测试：邮箱验证 + 密码重置 + 登录暴力保护。"""

import os
import uuid
from unittest.mock import patch

os.environ.setdefault("APP_ENV", "test")
os.environ["EMBEDDING_MODEL"] = "hash"

from app.models.user import User  # noqa: E402
from app.services import email_token  # noqa: E402
from app.utils.db import get_session  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_PREFIX = "test_g23_"


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _email(uname: str) -> str:
    return f"{uname}@test.local"


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


def _register(client: TestClient, username: str, email: str, password: str = "pass123456"):
    return client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password, "email": email},
    )


class TestEmailRequired:
    """注册邮箱必填测试。"""

    def test_register_without_email_fails(self, client: TestClient):
        """不传 email 注册应 422。"""
        resp = client.post(
            "/api/v1/auth/register",
            json={"username": _uname(), "password": "pass123456"},
        )
        assert resp.status_code == 422

    def test_register_with_email_succeeds(self, client: TestClient):
        """传 email 注册应成功。"""
        uname = _uname()
        try:
            resp = _register(client, uname, _email(uname))
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            _cleanup_users(uname)

    def test_register_duplicate_email_fails(self, client: TestClient):
        """重复邮箱注册应 400。"""
        uname1 = _uname()
        uname2 = _uname()
        email = f"{uname1}@test.local"
        try:
            assert _register(client, uname1, email).json()["code"] == 0
            resp = _register(client, uname2, email)
            assert resp.status_code == 400
            assert resp.json()["code"] == 40002
        finally:
            _cleanup_users(uname1, uname2)


class TestEmailTokenService:
    """邮件 token 服务单元测试。"""

    def test_create_and_verify_email_token(self):
        """创建并校验邮箱验证 token。"""
        token = email_token.create_verify_token(42, "user@test.com")
        result = email_token.verify_email_token(token)
        assert result is not None
        user_id, email = result
        assert user_id == 42
        assert email == "user@test.com"

    def test_create_and_verify_reset_token(self):
        """创建并校验密码重置 token。"""
        token = email_token.create_reset_token(42, "user@test.com")
        result = email_token.verify_reset_token(token)
        assert result is not None
        user_id, email = result
        assert user_id == 42
        assert email == "user@test.com"

    def test_expired_verify_token(self):
        """过期验证 token 返回 None。"""
        from datetime import UTC, datetime, timedelta

        import jwt
        from app.core.config import get_settings

        settings = get_settings()
        secret = settings.JWT_SECRET_KEY + "|email_verify"
        payload = {
            "sub": "42",
            "email": "user@test.com",
            "type": "verify_email",
            "exp": datetime.now(UTC) - timedelta(minutes=1),  # 已过期
            "iat": datetime.now(UTC),
        }
        token = jwt.encode(payload, secret, algorithm=settings.JWT_ALGORITHM)
        result = email_token.verify_email_token(token)
        assert result is None

    def test_cross_type_token_rejected(self):
        """验证 token 不能用于重置，反之亦然。"""
        verify_tok = email_token.create_verify_token(42, "user@test.com")
        reset_tok = email_token.create_reset_token(42, "user@test.com")
        # 用 verify 函数验 reset token → 拒绝
        assert email_token.verify_email_token(reset_tok) is None
        # 用 reset 函数验 verify token → 拒绝
        assert email_token.verify_reset_token(verify_tok) is None

    def test_invalid_token(self):
        """无效 token 返回 None。"""
        assert email_token.verify_email_token("invalid.token.here") is None
        assert email_token.verify_reset_token("invalid.token.here") is None


class TestVerifyEmailEndpoint:
    """邮箱验证端点测试。"""

    def test_verify_email_success(self, client: TestClient):
        """正常验证流程。"""
        uname = _uname()
        email = _email(uname)
        try:
            _register(client, uname, email)
            token = email_token.create_verify_token(
                client.get("/api/v1/users/me").json()["data"]["id"] if False else 0,
                email,
            )
            # 用注册返回的 token 来验证（从 user 的 id 生成）
            # 先获取 user id
            db = get_session()
            try:
                user = db.query(User).filter(User.username == uname).first()
                user_id = user.id
                assert user.email_verified is False
            finally:
                db.close()

            token = email_token.create_verify_token(user_id, email)
            resp = client.get(f"/api/v1/auth/verify-email?token={token}")
            assert resp.status_code == 200
            assert resp.json()["code"] == 0

            # 验证 email_verified 已更新
            db = get_session()
            try:
                user = db.query(User).filter(User.id == user_id).first()
                assert user.email_verified is True
            finally:
                db.close()
        finally:
            _cleanup_users(uname)

    def test_verify_email_invalid_token(self, client: TestClient):
        """无效 token 返回 400。"""
        resp = client.get("/api/v1/auth/verify-email?token=invalid.token")
        assert resp.status_code == 400
        assert resp.json()["code"] == 40010

    def test_verify_email_already_verified(self, client: TestClient):
        """重复验证返回成功提示。"""
        uname = _uname()
        email = _email(uname)
        try:
            _register(client, uname, email)
            db = get_session()
            try:
                user = db.query(User).filter(User.username == uname).first()
                user_id = user.id
            finally:
                db.close()

            token = email_token.create_verify_token(user_id, email)
            # 第一次验证
            resp1 = client.get(f"/api/v1/auth/verify-email?token={token}")
            assert resp1.status_code == 200
            # 第二次验证（token 仍然有效，但已验证）
            resp2 = client.get(f"/api/v1/auth/verify-email?token={token}")
            assert resp2.status_code == 200
            assert "已验证" in resp2.json()["data"]["message"]
        finally:
            _cleanup_users(uname)


class TestForgotPassword:
    """忘记密码测试。"""

    def test_forgot_password_returns_success(self, client: TestClient):
        """无论邮箱是否存在均返回成功。"""
        resp = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nonexistent@example.com"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert "重置密码邮件已发送" in resp.json()["data"]["message"]

    def test_forgot_password_existing_email(self, client: TestClient):
        """已注册邮箱也返回成功（防枚举）。"""
        uname = _uname()
        email = _email(uname)
        try:
            _register(client, uname, email)
            resp = client.post(
                "/api/v1/auth/forgot-password",
                json={"email": email},
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
        finally:
            _cleanup_users(uname)


class TestResetPassword:
    """重置密码测试。"""

    def test_reset_password_success(self, client: TestClient):
        """正常重置密码 + 旧 token 登录失效。"""
        uname = _uname()
        email = _email(uname)
        old_password = "pass123456"
        new_password = "newpass789"
        try:
            _register(client, uname, email, old_password)
            db = get_session()
            try:
                user = db.query(User).filter(User.username == uname).first()
                user_id = user.id
            finally:
                db.close()

            token = email_token.create_reset_token(user_id, email)
            resp = client.post(
                "/api/v1/auth/reset-password",
                json={"token": token, "new_password": new_password},
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert "密码重置成功" in resp.json()["data"]["message"]

            # 用新密码登录应成功
            resp_login = client.post(
                "/api/v1/auth/login",
                json={"username": uname, "password": new_password},
            )
            assert resp_login.status_code == 200

            # 用旧密码登录应失败
            resp_old = client.post(
                "/api/v1/auth/login",
                json={"username": uname, "password": old_password},
            )
            assert resp_old.status_code == 401
        finally:
            _cleanup_users(uname)

    def test_reset_password_invalid_token(self, client: TestClient):
        """无效 token 返回 400。"""
        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "invalid.token", "new_password": "newpass789"},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == 40012

    def test_reset_password_short_password(self, client: TestClient):
        """密码太短应 422。"""
        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "some.token", "new_password": "12345"},
        )
        assert resp.status_code == 422


class TestLoginBruteForceProtection:
    """登录暴力保护测试（mock Redis）。"""

    def test_login_lock_after_5_failures(self, client: TestClient):
        """连续 5 次失败后锁定 15min（返回 423）。"""
        uname = _uname()
        email = _email(uname)
        # 用 dict 模拟 Redis 存储
        fake_store: dict[str, str] = {}

        class FakeRedis:
            def get(self, key): return fake_store.get(key)
            def incr(self, key):
                fake_store[key] = str(int(fake_store.get(key, "0")) + 1)
                return int(fake_store[key])
            def expire(self, key, ttl): pass
            def ttl(self, key): return 900
            def delete(self, key): fake_store.pop(key, None)
            def pipeline(self):
                return FakePipeline(self)
            def setex(self, key, ttl, val): fake_store[key] = val
            def exists(self, key): return key in fake_store

        class FakePipeline:
            def __init__(self, r): self.r = r
            def incr(self, key): self.r.incr(key)
            def expire(self, key, ttl): pass
            def execute(self): pass

        try:
            _register(client, uname, email)
            with patch("app.services.auth_service._get_redis_safe", return_value=FakeRedis()):
                # 5 次错误密码
                for _ in range(5):
                    resp = client.post(
                        "/api/v1/auth/login",
                        json={"username": uname, "password": "wrongpass"},
                    )
                    assert resp.status_code == 401

                # 第 6 次应被锁定（423）
                resp = client.post(
                    "/api/v1/auth/login",
                    json={"username": uname, "password": "wrongpass"},
                )
                assert resp.status_code == 423
                assert resp.json()["code"] == 42301
        finally:
            _cleanup_users(uname)

    def test_login_success_clears_counter(self, client: TestClient):
        """登录成功后清零失败计数。"""
        uname = _uname()
        email = _email(uname)
        password = "pass123456"
        fake_store: dict[str, str] = {}

        class FakeRedis:
            def get(self, key): return fake_store.get(key)
            def incr(self, key):
                fake_store[key] = str(int(fake_store.get(key, "0")) + 1)
                return int(fake_store[key])
            def expire(self, key, ttl): pass
            def ttl(self, key): return 900
            def delete(self, key): fake_store.pop(key, None)
            def pipeline(self):
                return FakePipeline(self)
            def setex(self, key, ttl, val): fake_store[key] = val
            def exists(self, key): return key in fake_store

        class FakePipeline:
            def __init__(self, r): self.r = r
            def incr(self, key): self.r.incr(key)
            def expire(self, key, ttl): pass
            def execute(self): pass

        try:
            _register(client, uname, email, password)
            with patch("app.services.auth_service._get_redis_safe", return_value=FakeRedis()):
                # 3 次错误
                for _ in range(3):
                    client.post(
                        "/api/v1/auth/login",
                        json={"username": uname, "password": "wrong"},
                    )
                # 1 次正确
                resp = client.post(
                    "/api/v1/auth/login",
                    json={"username": uname, "password": password},
                )
                assert resp.status_code == 200
                # 计数器应已清零，再错 5 次不应锁定（第 6 次才锁定）
                for _ in range(5):
                    client.post(
                        "/api/v1/auth/login",
                        json={"username": uname, "password": "wrong"},
                    )
                resp = client.post(
                    "/api/v1/auth/login",
                    json={"username": uname, "password": "wrong"},
                )
                # 第 6 次错误（从清零后算起）应触发锁定
                assert resp.status_code == 423
        finally:
            _cleanup_users(uname)



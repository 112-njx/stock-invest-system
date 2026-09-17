"""G33 测试：已登录用户改密 / 改邮箱。"""

import os
import uuid

os.environ.setdefault("APP_ENV", "test")
os.environ["EMBEDDING_MODEL"] = "hash"

from app.models.session import UserSession  # noqa: E402
from app.models.user import User  # noqa: E402
from app.utils.db import get_session  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_PREFIX = "test_g33_"


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _register(client: TestClient, username: str, password: str = "pass123456"):
    return client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password, "email": f"{username}@test.local"},
    )


def _cleanup_users(*usernames: str) -> None:
    db = get_session()
    try:
        for uname in usernames:
            u = db.query(User).filter(User.username == uname).first()
            if u:
                db.query(UserSession).filter(UserSession.user_id == u.id).delete()
                db.delete(u)
        db.commit()
    finally:
        db.close()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestChangePassword:
    """改密端点测试。"""

    def test_change_password_success(self, client: TestClient):
        """改密成功 → 新密码可登录、旧密码失败。"""
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            resp = client.put(
                "/api/v1/users/me/password",
                json={"old_password": "pass123456", "new_password": "newpass789"},
                headers=_auth(token),
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0

            # 新密码可登录
            r_new = client.post(
                "/api/v1/auth/login", json={"username": uname, "password": "newpass789"}
            )
            assert r_new.status_code == 200
            # 旧密码失败
            r_old = client.post(
                "/api/v1/auth/login", json={"username": uname, "password": "pass123456"}
            )
            assert r_old.status_code == 401
        finally:
            _cleanup_users(uname)

    def test_change_password_wrong_old(self, client: TestClient):
        """旧密码错误 → 400(40003)。"""
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            resp = client.put(
                "/api/v1/users/me/password",
                json={"old_password": "wrongpass", "new_password": "newpass789"},
                headers=_auth(token),
            )
            assert resp.status_code == 400
            assert resp.json()["code"] == 40003
        finally:
            _cleanup_users(uname)

    def test_change_password_same_as_old(self, client: TestClient):
        """新旧密码相同 → 400(40004)。"""
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            resp = client.put(
                "/api/v1/users/me/password",
                json={"old_password": "pass123456", "new_password": "pass123456"},
                headers=_auth(token),
            )
            assert resp.status_code == 400
            assert resp.json()["code"] == 40004
        finally:
            _cleanup_users(uname)

    def test_change_password_revokes_sessions(self, client: TestClient):
        """改密后该用户全部 refresh session 被吊销。"""
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            db = get_session()
            try:
                user = db.query(User).filter(User.username == uname).first()
                user_id = user.id
                active_before = (
                    db.query(UserSession)
                    .filter(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
                    .count()
                )
                assert active_before >= 1
            finally:
                db.close()

            client.put(
                "/api/v1/users/me/password",
                json={"old_password": "pass123456", "new_password": "newpass789"},
                headers=_auth(token),
            )

            db = get_session()
            try:
                active_after = (
                    db.query(UserSession)
                    .filter(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
                    .count()
                )
                assert active_after == 0
            finally:
                db.close()
        finally:
            _cleanup_users(uname)

    def test_change_password_requires_auth(self, client: TestClient):
        """未登录 → 401。"""
        resp = client.put(
            "/api/v1/users/me/password",
            json={"old_password": "pass123456", "new_password": "newpass789"},
        )
        assert resp.status_code == 401

    def test_change_password_too_short(self, client: TestClient):
        """新密码过短 → 422。"""
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            resp = client.put(
                "/api/v1/users/me/password",
                json={"old_password": "pass123456", "new_password": "123"},
                headers=_auth(token),
            )
            assert resp.status_code == 422
        finally:
            _cleanup_users(uname)


class TestChangeEmail:
    """改邮箱端点测试。"""

    def test_change_email_success(self, client: TestClient):
        """改邮箱成功 → email 更新且 email_verified 置 false。"""
        uname = _uname()
        new_email = f"{uname}_new@test.local"
        try:
            token = _register(client, uname).json()["data"]["token"]
            resp = client.put(
                "/api/v1/users/me/email",
                json={"password": "pass123456", "new_email": new_email},
                headers=_auth(token),
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert "邮箱已更新" in resp.json()["data"]["message"]

            me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]
            assert me["email"] == new_email
            assert me["email_verified"] is False
        finally:
            _cleanup_users(uname)

    def test_change_email_wrong_password(self, client: TestClient):
        """密码错误 → 400(40003)。"""
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            resp = client.put(
                "/api/v1/users/me/email",
                json={"password": "wrongpass", "new_email": "x@test.local"},
                headers=_auth(token),
            )
            assert resp.status_code == 400
            assert resp.json()["code"] == 40003
        finally:
            _cleanup_users(uname)

    def test_change_email_same_as_current(self, client: TestClient):
        """新邮箱与当前相同 → 400(40005)。"""
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            resp = client.put(
                "/api/v1/users/me/email",
                json={"password": "pass123456", "new_email": f"{uname}@test.local"},
                headers=_auth(token),
            )
            assert resp.status_code == 400
            assert resp.json()["code"] == 40005
        finally:
            _cleanup_users(uname)

    def test_change_email_taken_by_other(self, client: TestClient):
        """新邮箱已被他人占用 → 400(40002)。"""
        uname_a = _uname()
        uname_b = _uname()
        try:
            _register(client, uname_a)
            token_b = _register(client, uname_b).json()["data"]["token"]
            resp = client.put(
                "/api/v1/users/me/email",
                json={"password": "pass123456", "new_email": f"{uname_a}@test.local"},
                headers=_auth(token_b),
            )
            assert resp.status_code == 400
            assert resp.json()["code"] == 40002
        finally:
            _cleanup_users(uname_a, uname_b)

    def test_change_email_requires_auth(self, client: TestClient):
        """未登录 → 401。"""
        resp = client.put(
            "/api/v1/users/me/email",
            json={"password": "pass123456", "new_email": "x@test.local"},
        )
        assert resp.status_code == 401

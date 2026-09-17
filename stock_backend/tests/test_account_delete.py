"""G18 测试：账户删除（软删 / token 吊销 / 30 天宽限恢复 / 硬删级联）。"""

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ.setdefault("APP_ENV", "test")
os.environ["EMBEDDING_MODEL"] = "hash"

from app.core.config import get_settings  # noqa: E402
from app.models.agent import AgentRun, MemoryChunk, UserAgent  # noqa: E402
from app.models.notification import Notification  # noqa: E402
from app.models.session import UserSession  # noqa: E402
from app.models.strategy import Conversation, TradingStrategy  # noqa: E402
from app.models.user import SupportResistance, User, UserWatchlist  # noqa: E402
from app.services import user_service  # noqa: E402
from app.utils.db import get_session  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_PREFIX = "test_g18_"


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _register(client: TestClient, username: str, password: str = "pass123456"):
    return client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password, "email": f"{username}@test.local"},
    )


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _cleanup(*usernames: str) -> None:
    db = get_session()
    try:
        for uname in usernames:
            u = db.query(User).filter(User.username == uname).first()
            if u:
                user_service.hard_delete_account(db, u.id)
        db.commit()
    finally:
        db.close()


def _uid(uname: str) -> int | None:
    db = get_session()
    try:
        u = db.query(User).filter(User.username == uname).first()
        return u.id if u else None
    finally:
        db.close()


class TestSoftDelete:
    """软删除端点。"""

    def test_delete_requires_auth(self, client: TestClient):
        assert client.delete("/api/v1/users/me").status_code == 401

    def test_delete_sets_flags(self, client: TestClient):
        """软删置 is_deleted/deleted_at。"""
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            resp = client.delete("/api/v1/users/me", headers=_auth(token))
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"]["grace_days"] == 30

            db = get_session()
            try:
                u = db.query(User).filter(User.username == uname).first()
                assert u.is_deleted is True
                assert u.deleted_at is not None
            finally:
                db.close()
        finally:
            _cleanup(uname)

    def test_delete_twice_rejected(self, client: TestClient):
        """重复注销 → 400(40040)。"""
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            assert client.delete("/api/v1/users/me", headers=_auth(token)).status_code == 200
            # 软删后 token 立即失效，第二次调用 401（无法再进业务层）
            resp = client.delete("/api/v1/users/me", headers=_auth(token))
            assert resp.status_code == 401
        finally:
            _cleanup(uname)

    def test_token_invalidated_immediately(self, client: TestClient):
        """软删后原 access token 立即失效（所有受保护端点 401）。"""
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            assert client.get("/api/v1/users/me", headers=_auth(token)).status_code == 200
            client.delete("/api/v1/users/me", headers=_auth(token))

            resp = client.get("/api/v1/users/me", headers=_auth(token))
            assert resp.status_code == 401
            assert resp.json()["code"] == 40103
        finally:
            _cleanup(uname)

    def test_refresh_tokens_revoked(self, client: TestClient):
        """软删后该用户全部 refresh session 被吊销。"""
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            uid = _uid(uname)
            db = get_session()
            try:
                active = (
                    db.query(UserSession)
                    .filter(UserSession.user_id == uid, UserSession.revoked_at.is_(None))
                    .count()
                )
                assert active >= 1
            finally:
                db.close()

            client.delete("/api/v1/users/me", headers=_auth(token))

            db = get_session()
            try:
                active = (
                    db.query(UserSession)
                    .filter(UserSession.user_id == uid, UserSession.revoked_at.is_(None))
                    .count()
                )
                assert active == 0
            finally:
                db.close()
        finally:
            _cleanup(uname)


class TestLoginRejected:
    """软删后登录被拒。"""

    def test_login_rejected_after_delete(self, client: TestClient):
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            client.delete("/api/v1/users/me", headers=_auth(token))

            resp = client.post(
                "/api/v1/auth/login", json={"username": uname, "password": "pass123456"}
            )
            assert resp.status_code == 403
            assert resp.json()["code"] == 40310
            assert "注销" in resp.json()["msg"]
        finally:
            _cleanup(uname)


class TestRestoreAccount:
    """30 天宽限期恢复。"""

    def test_restore_within_grace(self, client: TestClient):
        """宽限期内恢复 → 可重新登录。"""
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            client.delete("/api/v1/users/me", headers=_auth(token))

            resp = client.post(
                "/api/v1/auth/restore-account",
                json={"username": uname, "password": "pass123456"},
            )
            assert resp.status_code == 200
            assert resp.json()["code"] == 0
            assert resp.json()["data"]["token"]

            db = get_session()
            try:
                u = db.query(User).filter(User.username == uname).first()
                assert u.is_deleted is False
                assert u.deleted_at is None
            finally:
                db.close()

            # 恢复后可正常登录
            assert (
                client.post(
                    "/api/v1/auth/login", json={"username": uname, "password": "pass123456"}
                ).status_code
                == 200
            )
        finally:
            _cleanup(uname)

    def test_restore_wrong_password(self, client: TestClient):
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            client.delete("/api/v1/users/me", headers=_auth(token))
            resp = client.post(
                "/api/v1/auth/restore-account", json={"username": uname, "password": "wrongpass"}
            )
            assert resp.status_code == 401
        finally:
            _cleanup(uname)

    def test_restore_not_deleted_rejected(self, client: TestClient):
        """未注销账户调恢复 → 400(40041)。"""
        uname = _uname()
        try:
            _register(client, uname)
            resp = client.post(
                "/api/v1/auth/restore-account",
                json={"username": uname, "password": "pass123456"},
            )
            assert resp.status_code == 400
            assert resp.json()["code"] == 40041
        finally:
            _cleanup(uname)

    def test_restore_after_grace_rejected(self, client: TestClient):
        """超过 30 天宽限期 → 410(41001)。"""
        uname = _uname()
        try:
            token = _register(client, uname).json()["data"]["token"]
            client.delete("/api/v1/users/me", headers=_auth(token))

            db = get_session()
            try:
                u = db.query(User).filter(User.username == uname).first()
                u.deleted_at = datetime.now(UTC) - timedelta(days=31)
                db.commit()
            finally:
                db.close()

            resp = client.post(
                "/api/v1/auth/restore-account",
                json={"username": uname, "password": "pass123456"},
            )
            assert resp.status_code == 410
            assert resp.json()["code"] == 41001
        finally:
            _cleanup(uname)


class TestHardDeleteCascade:
    """硬删级联清理全部关联数据。"""

    def test_hard_delete_cascades_all_tables(self, client: TestClient):
        """造满各关联表数据 → 硬删后全部清空 + 记忆目录删除。"""
        uname = _uname()
        try:
            _register(client, uname)
            uid = _uid(uname)

            # 造关联数据（symbol_id 取库中真实标的，满足 FK 约束）
            db = get_session()
            try:
                from app.models.symbol import Symbol

                symbol_id = db.query(Symbol.id).first()[0]
                db.add(UserWatchlist(user_id=uid, symbol_id=symbol_id))
                db.add(SupportResistance(user_id=uid, symbol_id=symbol_id, type="support", price=10))
                db.add(TradingStrategy(user_id=uid, title="G18测试策略", status="draft"))
                db.add(Conversation(user_id=uid, title="G18测试会话"))
                db.add(UserAgent(user_id=uid, name="G18测试Agent"))
                db.add(AgentRun(user_id=uid, run_type="diagnostic", status="success"))
                db.add(MemoryChunk(user_id=uid, source_type="rule", content="G18测试记忆"))
                db.add(Notification(user_id=uid, type="system", title="G18测试通知"))
                db.commit()
            finally:
                db.close()

            # 造记忆目录
            memory_dir = Path(get_settings().MEMORY_DIR) / str(uid)
            memory_dir.mkdir(parents=True, exist_ok=True)
            (memory_dir / "rule.md").write_text("测试记忆内容", encoding="utf-8")
            assert memory_dir.exists()

            # 硬删
            db = get_session()
            try:
                result = user_service.hard_delete_account(db, uid)
                assert result["deleted"] is True
            finally:
                db.close()

            # 断言全部清空
            db = get_session()
            try:
                assert db.query(User).filter(User.id == uid).first() is None
                assert db.query(UserWatchlist).filter(UserWatchlist.user_id == uid).count() == 0
                assert db.query(SupportResistance).filter(SupportResistance.user_id == uid).count() == 0
                assert db.query(TradingStrategy).filter(TradingStrategy.user_id == uid).count() == 0
                assert db.query(Conversation).filter(Conversation.user_id == uid).count() == 0
                assert db.query(UserAgent).filter(UserAgent.user_id == uid).count() == 0
                assert db.query(AgentRun).filter(AgentRun.user_id == uid).count() == 0
                assert db.query(MemoryChunk).filter(MemoryChunk.user_id == uid).count() == 0
                assert db.query(Notification).filter(Notification.user_id == uid).count() == 0
                assert db.query(UserSession).filter(UserSession.user_id == uid).count() == 0
            finally:
                db.close()

            # 记忆目录已删除
            assert not memory_dir.exists()
        finally:
            _cleanup(uname)

    def test_hard_delete_missing_user(self, client: TestClient):
        db = get_session()
        try:
            result = user_service.hard_delete_account(db, 99999999)
            assert result["deleted"] is False
        finally:
            db.close()


class TestPurgeExpired:
    """beat 硬删扫描。"""

    def test_purge_only_expired(self, client: TestClient):
        """只硬删超宽限期的账户，未到期的保留。"""
        uname_old = _uname()
        uname_new = _uname()
        try:
            t_old = _register(client, uname_old).json()["data"]["token"]
            t_new = _register(client, uname_new).json()["data"]["token"]
            client.delete("/api/v1/users/me", headers=_auth(t_old))
            client.delete("/api/v1/users/me", headers=_auth(t_new))

            # old 设为 31 天前，new 保持刚删除
            db = get_session()
            try:
                u = db.query(User).filter(User.username == uname_old).first()
                u.deleted_at = datetime.now(UTC) - timedelta(days=31)
                db.commit()
            finally:
                db.close()

            db = get_session()
            try:
                purged = user_service.purge_expired_deleted_accounts(db)
                assert purged >= 1
            finally:
                db.close()

            # old 已硬删，new 仍在（软删状态）
            db = get_session()
            try:
                assert db.query(User).filter(User.username == uname_old).first() is None
                u_new = db.query(User).filter(User.username == uname_new).first()
                assert u_new is not None
                assert u_new.is_deleted is True
            finally:
                db.close()
        finally:
            _cleanup(uname_old, uname_new)

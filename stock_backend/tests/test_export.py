"""G17 测试：用户数据导出（异步任务 / 状态查询 / 签名下载 / 24h 清理）。"""

import os
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("APP_ENV", "test")
os.environ["EMBEDDING_MODEL"] = "hash"

from app.core.config import get_settings  # noqa: E402
from app.models.export_task import ExportTask  # noqa: E402
from app.models.strategy import Conversation, TradingStrategy  # noqa: E402
from app.models.user import User  # noqa: E402
from app.repositories import export_repo  # noqa: E402
from app.services import export_service, export_token  # noqa: E402
from app.utils.db import get_session  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_PREFIX = "test_g17_"


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _register(client: TestClient, username: str) -> tuple[str, int]:
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "pass123456", "email": f"{username}@test.local"},
    )
    data = resp.json()["data"]
    return data["token"], data["user"]["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _cleanup(*usernames: str) -> None:
    db = get_session()
    try:
        for uname in usernames:
            u = db.query(User).filter(User.username == uname).first()
            if u:
                rows = db.query(ExportTask).filter(ExportTask.user_id == u.id).all()
                for r in rows:
                    export_service.delete_export_file(r.file_path)
                db.query(ExportTask).filter(ExportTask.user_id == u.id).delete()
                db.query(TradingStrategy).filter(TradingStrategy.user_id == u.id).delete()
                db.query(Conversation).filter(Conversation.user_id == u.id).delete()
                db.delete(u)
        db.commit()
    finally:
        db.close()


class TestExportToken:
    """签名下载 token 单元测试。"""

    def test_create_and_verify(self):
        tok = export_token.create_download_token(7, 42)
        parsed = export_token.verify_download_token(tok)
        assert parsed is not None
        assert parsed == (7, 42)

    def test_invalid_token(self):
        assert export_token.verify_download_token("invalid.token.here") is None

    def test_expired_token(self):
        import jwt

        s = get_settings()
        payload = {
            "sub": "7",
            "task_id": 42,
            "type": "export_download",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
            "iat": datetime.now(UTC),
        }
        tok = jwt.encode(payload, s.JWT_SECRET_KEY + "|export_download", algorithm=s.JWT_ALGORITHM)
        assert export_token.verify_download_token(tok) is None

    def test_access_token_not_accepted(self):
        """access token 不能当下载 token 用（独立签名密钥）。"""
        from app.core.security import create_access_token

        assert export_token.verify_download_token(create_access_token(7)) is None


class TestCreateExport:
    """创建导出任务端点。"""

    def test_create_requires_auth(self, client: TestClient):
        assert client.post("/api/v1/users/me/export").status_code == 401

    def test_create_returns_pending(self, client: TestClient):
        """创建任务返回 task_id 与 pending/queued 状态（Celery 异步执行，测试中 mock）。"""
        uname = _uname()
        try:
            token, _ = _register(client, uname)
            with patch("app.worker.tasks.export_tasks.run_user_export.delay") as mock_delay:
                resp = client.post("/api/v1/users/me/export", headers=_auth(token))
                assert resp.status_code == 200
                body = resp.json()
                assert body["code"] == 0
                data = body["data"]
                assert data["task_id"] > 0
                assert data["status"] == "pending"
                assert data["download_url"] is None  # 未完成无下载链接
                mock_delay.assert_called_once()
        finally:
            _cleanup(uname)


class TestExportStatus:
    """导出状态查询端点。"""

    def test_status_not_found(self, client: TestClient):
        uname = _uname()
        try:
            token, _ = _register(client, uname)
            resp = client.get("/api/v1/users/me/export/999999", headers=_auth(token))
            assert resp.status_code == 404
            assert resp.json()["code"] == 40420
        finally:
            _cleanup(uname)

    def test_status_other_user_404(self, client: TestClient):
        """越权查询他人导出任务 → 404。"""
        uname_a = _uname()
        uname_b = _uname()
        try:
            token_a, _ = _register(client, uname_a)
            _, uid_b = _register(client, uname_b)
            db = get_session()
            try:
                row = export_repo.create(db, uid_b)
                db.commit()
                task_id = row.id
            finally:
                db.close()
            resp = client.get(f"/api/v1/users/me/export/{task_id}", headers=_auth(token_a))
            assert resp.status_code == 404
        finally:
            _cleanup(uname_a, uname_b)

    def test_status_success_has_download_url(self, client: TestClient):
        """成功后状态接口返回带签名 token 的下载链接。"""
        uname = _uname()
        try:
            token, uid = _register(client, uname)
            # 直接跑同步打包（不依赖 Celery worker）
            db = get_session()
            try:
                row = export_repo.create(db, uid)
                db.commit()
                task_id = row.id
                export_service.build_export_zip(db, task_id)
            finally:
                db.close()

            resp = client.get(f"/api/v1/users/me/export/{task_id}", headers=_auth(token))
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["status"] == "success"
            assert data["progress"] == 100
            assert data["file_size"] > 0
            assert data["download_url"] and "token=" in data["download_url"]
            assert data["expires_at"] is not None
        finally:
            _cleanup(uname)


class TestExportZipContent:
    """ZIP 内容完整性（服务层）。"""

    def test_zip_contains_all_domains(self, client: TestClient):
        """ZIP 覆盖：用户/关注/支撑压力/策略(JSON+代码)/回测/会话/Agent/记忆。"""
        uname = _uname()
        try:
            _, uid = _register(client, uname)
            db = get_session()
            try:
                # 造一条策略数据（含代码），验证 strategies/code/*.py 落盘
                db.add(
                    TradingStrategy(
                        user_id=uid, title="导出测试策略", code="def on_bar(bar, context): pass", status="draft"
                    )
                )
                db.add(Conversation(user_id=uid, title="导出测试会话"))
                db.commit()

                row = export_repo.create(db, uid)
                db.commit()
                task_id = row.id
                zip_path = export_service.build_export_zip(db, task_id)
            finally:
                db.close()

            assert zip_path.exists()
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                for required in [
                    "user.json",
                    "watchlist.json",
                    "support_resistance.json",
                    "strategies/strategies.json",
                    "backtest.json",
                    "conversations.json",
                    "agents.json",
                    "memory/facts.json",
                ]:
                    assert required in names, f"missing {required}"
                # 策略代码单独成文件
                assert any(n.startswith("strategies/code/strategy_") and n.endswith(".py") for n in names)
                # 用户 JSON 内容正确
                import json

                user_json = json.loads(zf.read("user.json").decode("utf-8"))
                assert user_json["username"] == uname
                assert user_json["email"] == f"{uname}@test.local"
                # 会话 JSON 含消息数组
                convs = json.loads(zf.read("conversations.json").decode("utf-8"))
                assert any(c["title"] == "导出测试会话" for c in convs)
        finally:
            _cleanup(uname)

    def test_build_fails_for_missing_task(self, client: TestClient):
        db = get_session()
        try:
            try:
                export_service.build_export_zip(db, 999999)
                raise AssertionError("should raise")
            except ValueError as e:
                assert "不存在" in str(e)
        finally:
            db.close()


class TestExportDownload:
    """签名下载端点。"""

    def test_download_with_valid_token(self, client: TestClient):
        uname = _uname()
        try:
            token, uid = _register(client, uname)
            db = get_session()
            try:
                row = export_repo.create(db, uid)
                db.commit()
                task_id = row.id
                export_service.build_export_zip(db, task_id)
            finally:
                db.close()

            status = client.get(f"/api/v1/users/me/export/{task_id}", headers=_auth(token)).json()["data"]
            url = status["download_url"]

            resp = client.get(url)
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/zip"
            assert len(resp.content) > 0
        finally:
            _cleanup(uname)

    def test_download_without_token_422(self, client: TestClient):
        assert client.get("/api/v1/users/me/export/1/download").status_code == 422

    def test_download_with_bad_token_403(self, client: TestClient):
        resp = client.get("/api/v1/users/me/export/1/download?token=bogus.token")
        assert resp.status_code == 403
        assert resp.json()["code"] == 40301

    def test_download_token_task_mismatch_403(self, client: TestClient):
        """token 属于另一个 task_id → 403（防越权）。"""
        uname = _uname()
        try:
            token, uid = _register(client, uname)
            db = get_session()
            try:
                row1 = export_repo.create(db, uid)
                row2 = export_repo.create(db, uid)
                db.commit()
                t1, t2 = row1.id, row2.id
                export_service.build_export_zip(db, t1)
            finally:
                db.close()

            status = client.get(f"/api/v1/users/me/export/{t1}", headers=_auth(token)).json()["data"]
            url = status["download_url"].replace(f"/{t1}/download", f"/{t2}/download")
            resp = client.get(url)
            assert resp.status_code == 403
        finally:
            _cleanup(uname)

    def test_download_pending_task_400(self, client: TestClient):
        """任务未完成 → 400。"""
        uname = _uname()
        try:
            token, uid = _register(client, uname)
            db = get_session()
            try:
                row = export_repo.create(db, uid)
                db.commit()
                task_id = row.id
            finally:
                db.close()
            dl_token = export_token.create_download_token(uid, task_id)
            resp = client.get(f"/api/v1/users/me/export/{task_id}/download?token={dl_token}")
            assert resp.status_code == 400
            assert resp.json()["code"] == 40030
        finally:
            _cleanup(uname)

    def test_download_missing_file_404(self, client: TestClient):
        """文件已被清理但状态仍 success → 404。"""
        uname = _uname()
        try:
            token, uid = _register(client, uname)
            db = get_session()
            try:
                row = export_repo.create(db, uid)
                db.commit()
                task_id = row.id
                zip_path = export_service.build_export_zip(db, task_id)
            finally:
                db.close()
            Path(zip_path).unlink()  # 模拟文件被清理

            dl_token = export_token.create_download_token(uid, task_id)
            resp = client.get(f"/api/v1/users/me/export/{task_id}/download?token={dl_token}")
            assert resp.status_code == 404
            assert resp.json()["code"] == 40421
        finally:
            _cleanup(uname)


class TestExportCleanup:
    """24h 过期清理。"""

    def test_cleanup_deletes_expired_file(self, client: TestClient):
        uname = _uname()
        try:
            _, uid = _register(client, uname)
            db = get_session()
            try:
                row = export_repo.create(db, uid)
                db.commit()
                task_id = row.id
                zip_path = export_service.build_export_zip(db, task_id)
                assert Path(zip_path).exists()

                # 人为把过期时间提前
                row = export_repo.get(db, task_id)
                row.expires_at = datetime.now(UTC) - timedelta(hours=1)
                db.commit()

                cleaned = export_service.cleanup_expired_exports(db)
                assert cleaned >= 1

                row = export_repo.get(db, task_id)
                assert row.status == "expired"
                assert row.file_path is None
                assert not Path(zip_path).exists()
            finally:
                db.close()
        finally:
            _cleanup(uname)

    def test_cleanup_skips_unexpired(self, client: TestClient):
        uname = _uname()
        try:
            _, uid = _register(client, uname)
            db = get_session()
            try:
                row = export_repo.create(db, uid, expires_at=datetime.now(UTC) + timedelta(hours=24))
                db.commit()
                task_id = row.id
                zip_path = export_service.build_export_zip(db, task_id)

                export_service.cleanup_expired_exports(db)

                row = export_repo.get(db, task_id)
                assert row.status == "success"
                assert Path(zip_path).exists()
            finally:
                db.close()
        finally:
            _cleanup(uname)

    def test_delete_export_file_idempotent(self):
        assert export_service.delete_export_file(None) is False
        assert export_service.delete_export_file("D:/nonexistent/file.zip") is False

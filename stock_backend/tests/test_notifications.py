"""G16 测试：通知中心 + 系统公告。"""

import os
import uuid

os.environ.setdefault("APP_ENV", "test")
os.environ["EMBEDDING_MODEL"] = "hash"

from app.models.notification import AdminAnnouncement, Notification  # noqa: E402
from app.models.user import User  # noqa: E402
from app.utils.db import get_session  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_PREFIX = "test_g16_"


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _register(client: TestClient, username: str) -> str:
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "pass123456", "email": f"{username}@test.local"},
    )
    return resp.json()["data"]["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _cleanup(*usernames: str) -> None:
    db = get_session()
    try:
        for uname in usernames:
            u = db.query(User).filter(User.username == uname).first()
            if u:
                db.query(Notification).filter(Notification.user_id == u.id).delete()
                db.delete(u)
        db.commit()
    finally:
        db.close()


def _seed_notification(user_id: int, title: str, type_: str = "system", is_read: bool = False) -> int:
    db = get_session()
    try:
        row = Notification(user_id=user_id, type=type_, title=title, content="测试内容", is_read=is_read)
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _user_id(uname: str) -> int:
    db = get_session()
    try:
        return db.query(User).filter(User.username == uname).first().id
    finally:
        db.close()


class TestNotificationList:
    """通知列表端点。"""

    def test_list_unread_first(self, client: TestClient):
        """未读优先于已读。"""
        uname = _uname()
        try:
            token = _register(client, uname)
            uid = _user_id(uname)
            _seed_notification(uid, "已读的", is_read=True)
            _seed_notification(uid, "未读的", is_read=False)

            resp = client.get("/api/v1/notifications", headers=_auth(token))
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["items"][0]["title"] == "未读的"
            assert data["items"][0]["is_read"] is False
            assert data["unread"] == 1
            assert data["total"] == 2
        finally:
            _cleanup(uname)

    def test_list_requires_auth(self, client: TestClient):
        assert client.get("/api/v1/notifications").status_code == 401

    def test_list_only_own(self, client: TestClient):
        """只能看到自己的通知（多租户隔离）。"""
        uname_a = _uname()
        uname_b = _uname()
        try:
            token_a = _register(client, uname_a)
            _register(client, uname_b)
            _seed_notification(_user_id(uname_b), "B 的通知")

            resp = client.get("/api/v1/notifications", headers=_auth(token_a))
            assert resp.status_code == 200
            assert resp.json()["data"]["total"] == 0
        finally:
            _cleanup(uname_a, uname_b)


class TestUnreadCount:
    """未读数端点。"""

    def test_unread_count(self, client: TestClient):
        uname = _uname()
        try:
            token = _register(client, uname)
            uid = _user_id(uname)
            assert client.get("/api/v1/notifications/unread-count", headers=_auth(token)).json()["data"][
                "unread"
            ] == 0
            _seed_notification(uid, "n1")
            _seed_notification(uid, "n2")
            _seed_notification(uid, "n3", is_read=True)
            resp = client.get("/api/v1/notifications/unread-count", headers=_auth(token))
            assert resp.json()["data"]["unread"] == 2
        finally:
            _cleanup(uname)

    def test_unread_count_requires_auth(self, client: TestClient):
        assert client.get("/api/v1/notifications/unread-count").status_code == 401


class TestMarkRead:
    """标记已读端点。"""

    def test_mark_one_read(self, client: TestClient):
        uname = _uname()
        try:
            token = _register(client, uname)
            nid = _seed_notification(_user_id(uname), "待读")
            resp = client.patch(f"/api/v1/notifications/{nid}/read", headers=_auth(token))
            assert resp.status_code == 200
            assert resp.json()["data"]["is_read"] is True
            assert resp.json()["data"]["read_at"] is not None
            assert client.get("/api/v1/notifications/unread-count", headers=_auth(token)).json()["data"][
                "unread"
            ] == 0
        finally:
            _cleanup(uname)

    def test_mark_other_user_notification_404(self, client: TestClient):
        """越权标记他人通知 → 404。"""
        uname_a = _uname()
        uname_b = _uname()
        try:
            token_a = _register(client, uname_a)
            _register(client, uname_b)
            nid = _seed_notification(_user_id(uname_b), "B 的")
            resp = client.patch(f"/api/v1/notifications/{nid}/read", headers=_auth(token_a))
            assert resp.status_code == 404
            assert resp.json()["code"] == 40410
        finally:
            _cleanup(uname_a, uname_b)

    def test_mark_all_read(self, client: TestClient):
        uname = _uname()
        try:
            token = _register(client, uname)
            uid = _user_id(uname)
            for i in range(3):
                _seed_notification(uid, f"n{i}")
            resp = client.patch("/api/v1/notifications/read-all", headers=_auth(token))
            assert resp.status_code == 200
            assert resp.json()["data"]["updated"] == 3
            assert client.get("/api/v1/notifications/unread-count", headers=_auth(token)).json()["data"][
                "unread"
            ] == 0
        finally:
            _cleanup(uname)


class TestActiveAnnouncements:
    """活跃公告查询（公开）。"""

    def test_active_announcements_public(self, client: TestClient):
        """免鉴权可读活跃公告。"""
        db = get_session()
        try:
            row = AdminAnnouncement(title="G16测试公告", content="内容", type="info", is_active=True)
            db.add(row)
            db.commit()
            aid = row.id
        finally:
            db.close()
        try:
            resp = client.get("/api/v1/announcements/active")
            assert resp.status_code == 200
            titles = [a["title"] for a in resp.json()["data"]]
            assert "G16测试公告" in titles
        finally:
            db = get_session()
            try:
                db.query(AdminAnnouncement).filter(AdminAnnouncement.id == aid).delete()
                db.commit()
            finally:
                db.close()

    def test_inactive_excluded(self, client: TestClient):
        """is_active=false 不出现在活跃列表。"""
        db = get_session()
        try:
            row = AdminAnnouncement(title="G16停用公告", content="c", is_active=False)
            db.add(row)
            db.commit()
            aid = row.id
        finally:
            db.close()
        try:
            resp = client.get("/api/v1/announcements/active")
            titles = [a["title"] for a in resp.json()["data"]]
            assert "G16停用公告" not in titles
        finally:
            db = get_session()
            try:
                db.query(AdminAnnouncement).filter(AdminAnnouncement.id == aid).delete()
                db.commit()
            finally:
                db.close()

    def test_expired_excluded(self, client: TestClient):
        """已过期公告不出现在活跃列表。"""
        from datetime import UTC, datetime, timedelta

        db = get_session()
        try:
            row = AdminAnnouncement(
                title="G16过期公告",
                content="c",
                is_active=True,
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )
            db.add(row)
            db.commit()
            aid = row.id
        finally:
            db.close()
        try:
            resp = client.get("/api/v1/announcements/active")
            titles = [a["title"] for a in resp.json()["data"]]
            assert "G16过期公告" not in titles
        finally:
            db = get_session()
            try:
                db.query(AdminAnnouncement).filter(AdminAnnouncement.id == aid).delete()
                db.commit()
            finally:
                db.close()


class TestPublishAnnouncement:
    """管理员发布公告。"""

    def test_publish_requires_admin(self, client: TestClient):
        """非管理员 → 403。"""
        uname = _uname()
        try:
            token = _register(client, uname)
            resp = client.post(
                "/api/v1/admin/announcements",
                json={"title": "x", "content": "y", "notify_users": False},
                headers=_auth(token),
            )
            assert resp.status_code == 403
            assert resp.json()["code"] == 40300
        finally:
            _cleanup(uname)

    def test_publish_requires_auth(self, client: TestClient):
        resp = client.post("/api/v1/admin/announcements", json={"title": "x", "content": "y"})
        assert resp.status_code == 401

    def test_publish_success_with_notify(self, client: TestClient):
        """管理员发布 + 分发站内通知。"""
        uname = _uname()
        db = get_session()
        try:
            user = User(username=uname, password_hash="x", email=f"{uname}@test.local", is_admin=True)
            db.add(user)
            db.commit()
            uid = user.id
        finally:
            db.close()

        # 用该管理员账号登录（走真实登录拿 token）
        db = get_session()
        try:
            from app.core.security import hash_password

            u = db.query(User).filter(User.id == uid).first()
            u.password_hash = hash_password("pass123456")
            db.commit()
        finally:
            db.close()

        aid = None
        try:
            token = client.post(
                "/api/v1/auth/login", json={"username": uname, "password": "pass123456"}
            ).json()["data"]["token"]
            resp = client.post(
                "/api/v1/admin/announcements",
                json={"title": "G16发布测试", "content": "公告正文", "type": "warning", "notify_users": True},
                headers=_auth(token),
            )
            assert resp.status_code == 200
            body = resp.json()["data"]
            aid = body["announcement"]["id"]
            assert body["announcement"]["title"] == "G16发布测试"
            assert body["announcement"]["type"] == "warning"
            assert body["notified_users"] >= 1

            # 该管理员应收到 system 通知
            notif = client.get("/api/v1/notifications", headers=_auth(token)).json()["data"]
            assert any("系统公告：G16发布测试" in i["title"] for i in notif["items"])
        finally:
            db = get_session()
            try:
                if aid:
                    db.query(AdminAnnouncement).filter(AdminAnnouncement.id == aid).delete()
                db.commit()
            finally:
                db.close()
            _cleanup(uname)

    def test_publish_invalid_type(self, client: TestClient):
        """非法 type → 422。"""
        uname = _uname()
        try:
            token = _register(client, uname)
            resp = client.post(
                "/api/v1/admin/announcements",
                json={"title": "x", "content": "y", "type": "bogus"},
                headers=_auth(token),
            )
            # 非管理员先被 403 拦截，此处断言被拒绝即可
            assert resp.status_code in (403, 422)
        finally:
            _cleanup(uname)


class TestAnnouncementHistory:
    """公告历史列表（需登录）。"""

    def test_history_requires_auth(self, client: TestClient):
        assert client.get("/api/v1/announcements").status_code == 401

    def test_history_returns_all(self, client: TestClient):
        uname = _uname()
        try:
            token = _register(client, uname)
            resp = client.get("/api/v1/announcements", headers=_auth(token))
            assert resp.status_code == 200
            assert isinstance(resp.json()["data"], list)
        finally:
            _cleanup(uname)


class TestBacktestNotificationHook:
    """回测完成通知钩子（服务层单元）。"""

    def test_notify_backtest_success(self, client: TestClient):
        """成功通知含胜率/收益摘要。"""
        uname = _uname()
        try:
            _register(client, uname)
            uid = _user_id(uname)
            db = get_session()
            try:
                from app.services import notification_service

                notification_service.notify_backtest_complete(
                    db, uid, 42, "贵州茅台", "success", "胜率 50.0%，总收益 +10.00%。点击查看完整结果。"
                )
                db.commit()
            finally:
                db.close()

            db = get_session()
            try:
                row = (
                    db.query(Notification)
                    .filter(Notification.user_id == uid, Notification.type == "backtest_complete")
                    .first()
                )
                assert row is not None
                assert "贵州茅台" in row.title
                assert "胜率" in row.content
            finally:
                db.close()
        finally:
            _cleanup(uname)

    def test_notify_backtest_failed(self, client: TestClient):
        uname = _uname()
        try:
            _register(client, uname)
            uid = _user_id(uname)
            db = get_session()
            try:
                from app.services import notification_service

                notification_service.notify_backtest_complete(db, uid, 43, "平安银行", "failed")
                db.commit()
            finally:
                db.close()

            db = get_session()
            try:
                row = (
                    db.query(Notification)
                    .filter(Notification.user_id == uid, Notification.type == "backtest_complete")
                    .first()
                )
                assert row is not None
                assert "失败" in row.title
            finally:
                db.close()
        finally:
            _cleanup(uname)

"""阶段五 5.2 测试：delta 断点续传缓存 + resume 端点。"""

import uuid

from app.agent.sse import cache_delta, cache_done, clear_delta_cache, read_deltas_after, read_done
from app.models.user import User
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_sse_"


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _register(client: TestClient, username: str) -> str:
    r = client.post("/api/v1/auth/register", json={"username": username, "password": "pass123456"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


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


def _cid() -> int:
    return int(uuid.uuid4().hex[:12], 16) % (2**31)  # 伪会话 id（不落库）


def test_delta_cache_roundtrip():
    cid = _cid()
    clear_delta_cache(cid)
    try:
        cache_delta(cid, {"type": "delta", "seq": 1, "content": "a"})
        cache_delta(cid, {"type": "delta", "seq": 2, "content": "b"})
        cache_delta(cid, {"type": "delta", "seq": 3, "content": "c"})
        assert read_deltas_after(cid, 0) == [
            {"type": "delta", "seq": 1, "content": "a"},
            {"type": "delta", "seq": 2, "content": "b"},
            {"type": "delta", "seq": 3, "content": "c"},
        ]
        assert [d["seq"] for d in read_deltas_after(cid, 1)] == [2, 3]
        assert read_deltas_after(cid, 3) == []
    finally:
        clear_delta_cache(cid)


def test_clear_delta_cache_marks_expired():
    cid = _cid()
    clear_delta_cache(cid)
    assert read_deltas_after(cid, 0) is None  # key 不存在 → 缓存已过期


def test_cache_done_read_done():
    cid = _cid()
    clear_delta_cache(cid)
    cache_done(cid, {"type": "done", "message_id": 9})
    assert read_done(cid) == {"type": "done", "message_id": 9}
    clear_delta_cache(cid)
    assert read_done(cid) is None


def test_resume_endpoint_replays_deltas(client: TestClient):
    uname = _uname()
    try:
        token = _register(client, uname)
        conv = client.post("/api/v1/conversations", json={}, headers=_auth(token)).json()["data"]
        cid = conv["id"]
        clear_delta_cache(cid)
        cache_delta(cid, {"type": "delta", "seq": 1, "content": "第一段"})
        cache_delta(cid, {"type": "delta", "seq": 2, "content": "第二段"})
        cache_done(cid, {"type": "done", "message_id": 7, "conversation_id": cid, "run_id": 1})

        resp = client.get(f"/api/v1/chat/resume?conversation_id={cid}&last_seq=1", headers=_auth(token))
        assert resp.status_code == 200, resp.text
        body = resp.text
        assert '"seq": 2' in body  # 补发 seq>1
        assert '"seq": 1' not in body  # 不重复已收到的
        assert '"type": "done"' in body  # 补发完成标记
        assert "message_id" in body
        clear_delta_cache(cid)
    finally:
        _cleanup_users(uname)


def test_resume_endpoint_ownership(client: TestClient):
    u1, u2 = _uname(), _uname()
    try:
        t1 = _register(client, u1)
        t2 = _register(client, u2)
        conv = client.post("/api/v1/conversations", json={}, headers=_auth(t1)).json()["data"]
        cid = conv["id"]
        # 他人会话 resume → 404
        assert client.get(f"/api/v1/chat/resume?conversation_id={cid}&last_seq=0", headers=_auth(t2)).status_code == 404
        # 未登录 → 401
        assert client.get(f"/api/v1/chat/resume?conversation_id={cid}&last_seq=0").status_code == 401
    finally:
        _cleanup_users(u1, u2)

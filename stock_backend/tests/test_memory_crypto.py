"""G15（P0-3a）/ G34（P0-3b）测试：记忆文件 AES-256-GCM 加解密、审计日志、content 加密后检索解密。

密钥来源：测试用 monkeypatch 注入 32 字节随机密钥（不依赖 .env，也不硬编码密钥）。
"""

import secrets
import uuid
from pathlib import Path

import pytest
from app.agent.memory import memory_service, store
from app.core import crypto
from app.models.agent import MemoryChunk
from app.models.audit import AuditLog
from app.models.user import User
from app.repositories import audit_repo
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_enc_"


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    """注入随机测试密钥（32 字节 → 64 位 hex），并清缓存避免跨用例串扰。"""
    monkeypatch.setattr(crypto.settings, "MEMORY_ENCRYPTION_KEY", secrets.token_hex(32))
    crypto._cached_key.cache_clear()
    yield
    crypto._cached_key.cache_clear()


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _register(client: TestClient, username: str) -> dict:
    r = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "pass123456", "email": f"{username}@test.local"},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["user"]


def _cleanup(user_id: int, uname: str, tmp_memory: str) -> None:
    import shutil

    db = get_session()
    try:
        db.query(AuditLog).filter(AuditLog.user_id == user_id).delete()
        db.query(MemoryChunk).filter(MemoryChunk.user_id == user_id).delete()
        db.query(User).filter(User.username == uname).delete()
        db.commit()
    finally:
        db.close()
    d = Path(tmp_memory)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    memory_dir = str(tmp_path / "memory")
    monkeypatch.setattr(store.settings, "MEMORY_DIR", memory_dir)
    return {"memory": memory_dir}


# ---- crypto 基础 ----
def test_crypto_roundtrip_and_randomized_ciphertext():
    """加解密往返正确；同一明文两次加密结果不同（随机 nonce）。"""
    c1 = crypto.encrypt_str("止损不超过2%")
    c2 = crypto.encrypt_str("止损不超过2%")
    assert c1 != c2, "两次加密结果相同 → nonce 未随机化"
    assert crypto.decrypt_str(c1) == "止损不超过2%"
    assert crypto.decrypt_str(c2) == "止损不超过2%"
    assert "止损" not in c1, "密文中不应出现明文"


def test_crypto_decrypts_legacy_plaintext_as_is():
    """存量明文（无密文头）原样返回，保证迁移期可读。"""
    assert crypto.decrypt_str("明文记忆内容") == "明文记忆内容"
    assert crypto.decrypt_bytes("明文".encode()) == "明文".encode()
    assert crypto.is_encrypted(crypto.encrypt_bytes(b"x")) is True
    assert crypto.is_encrypted(b"plain") is False


def test_crypto_missing_key_raises_not_silent_plaintext(monkeypatch):
    """密钥未配置时必须明确报错，绝不静默降级为明文。"""
    monkeypatch.setattr(crypto.settings, "MEMORY_ENCRYPTION_KEY", "")
    crypto._cached_key.cache_clear()
    assert crypto.is_configured() is False
    with pytest.raises(crypto.EncryptionKeyMissing):
        crypto.encrypt_str("x")
    crypto._cached_key.cache_clear()


def test_crypto_rejects_wrong_key_length(monkeypatch):
    """密钥长度不符（非 32 字节）直接报错。"""
    monkeypatch.setattr(crypto.settings, "MEMORY_ENCRYPTION_KEY", "abcd")
    crypto._cached_key.cache_clear()
    with pytest.raises(crypto.EncryptionError):
        crypto.encrypt_str("x")
    crypto._cached_key.cache_clear()


def test_crypto_tampered_ciphertext_detected():
    """GCM 认证：密文被篡改后解密失败而非返回垃圾数据。"""
    blob = bytearray(crypto.encrypt_bytes(b"sensitive"))
    blob[-1] ^= 0x01
    with pytest.raises(crypto.EncryptionError):
        crypto.decrypt_bytes(bytes(blob))


# ---- G15：记忆文件加密 ----
def test_memory_file_written_encrypted_and_readable(client: TestClient, env):
    """记忆文件落盘为密文，读取可解密还原（明文不出现在磁盘上）。"""
    uname = _uname()
    user = _register(client, uname)
    try:
        fpath = store.append_to_memory_file(user["id"], "rule", "止损不超过2%", 8)
        raw = Path(fpath).read_bytes()
        assert crypto.is_encrypted(raw), "记忆文件未加密落盘"
        assert "止损不超过2%".encode() not in raw, "密文中泄漏明文"
        text0 = store.read_memory_file_text(fpath)
        assert text0.startswith("- [") and "止损不超过2%" in text0, "解密后应还原 markdown 行格式"

        # 追加第二条：仍为密文，且两条都在
        store.append_to_memory_file(user["id"], "rule", "单笔仓位不超过一成", 7)
        raw2 = Path(fpath).read_bytes()
        assert crypto.is_encrypted(raw2)
        text = store.read_memory_file_text(fpath)
        assert "止损不超过2%" in text and "单笔仓位不超过一成" in text
    finally:
        _cleanup(user["id"], uname, env["memory"])


def test_memory_file_reads_legacy_plaintext(tmp_path, env):
    """存量明文 .md 仍可读（迁移兼容）。"""
    d = Path(env["memory"]) / "999999"
    d.mkdir(parents=True, exist_ok=True)
    legacy = d / "rule.md"
    legacy.write_text("- [2026-01-01 10:00] (重要度8) 历史明文记忆\n", encoding="utf-8")
    assert "历史明文记忆" in store.read_memory_file_text(legacy)


# ---- G15：审计日志 ----
def test_audit_log_records_write_read_delete(client: TestClient, env):
    """记忆写入 / 读取 / 删除均落 audit_log。"""
    uname = _uname()
    user = _register(client, uname)
    uid = user["id"]
    try:
        db = get_session()
        try:
            memory_service.save_memory(db, uid, "rule", None, [{"content": "止损不超过2%", "type": "rule", "importance": 8}])
        finally:
            db.close()

        db = get_session()
        try:
            assert audit_repo.count_logs(db, uid, audit_repo.ACTION_WRITE) == 1
        finally:
            db.close()

        # 检索命中 → 记 read
        db = get_session()
        try:
            text = memory_service.retrieve_memory(db, uid, "止损", top_k=3)
            assert "止损" in text
        finally:
            db.close()
        db = get_session()
        try:
            assert audit_repo.count_logs(db, uid, audit_repo.ACTION_READ) == 1
        finally:
            db.close()

        # 删除 → 记 delete
        db = get_session()
        try:
            chunk = db.query(MemoryChunk).filter(MemoryChunk.user_id == uid).first()
            fact_id = chunk.id
        finally:
            db.close()
        db = get_session()
        try:
            assert memory_service.delete_fact(db, uid, fact_id) is True
        finally:
            db.close()
        db = get_session()
        try:
            logs = audit_repo.list_logs(db, uid, action=audit_repo.ACTION_DELETE)
            assert len(logs) == 1
            assert logs[0].memory_id == fact_id
        finally:
            db.close()
    finally:
        _cleanup(uid, uname, env["memory"])


def test_audit_log_isolated_by_user(client: TestClient, env):
    """审计日志按用户隔离。"""
    uname_a, uname_b = _uname(), _uname()
    ua = _register(client, uname_a)
    ub = _register(client, uname_b)
    try:
        db = get_session()
        try:
            memory_service.save_memory(db, ua["id"], "rule", None, [{"content": "A 的止损规则", "type": "rule", "importance": 8}])
            assert audit_repo.count_logs(db, ua["id"]) == 1
            assert audit_repo.count_logs(db, ub["id"]) == 0
        finally:
            db.close()
    finally:
        _cleanup(ua["id"], uname_a, env["memory"])
        _cleanup(ub["id"], uname_b, env["memory"])


def test_audit_endpoint_requires_auth_and_returns_logs(client: TestClient, env):
    """GET /memory/audit 未登录 401；登录后返回本人审计。"""
    assert client.get("/api/v1/memory/audit").status_code == 401

    uname = _uname()
    user = _register(client, uname)
    uid = user["id"]
    try:
        r = client.post("/api/v1/auth/login", json={"username": uname, "password": "pass123456"})
        assert r.status_code == 200, r.text
        token = r.json()["data"]["token"]

        db = get_session()
        try:
            memory_service.save_memory(db, uid, "rule", None, [{"content": "止损不超过2%", "type": "rule", "importance": 8}])
        finally:
            db.close()

        r = client.get("/api/v1/memory/audit", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["action"] == "memory_write"
        assert data["items"][0]["id"] > 0
    finally:
        _cleanup(uid, uname, env["memory"])


# ---- G34：content 加密落库 ----
def test_memory_chunk_content_stored_encrypted_and_decrypted_on_read(client: TestClient, env):
    """content 落库为密文（直读原始列验证），ORM 读出为明文，检索返回解密原文。"""
    from sqlalchemy import text as sa_text

    uname = _uname()
    user = _register(client, uname)
    uid = user["id"]
    try:
        db = get_session()
        try:
            memory_service.save_memory(db, uid, "rule", None, [{"content": "止损不超过2%", "type": "rule", "importance": 8}])
        finally:
            db.close()

        # 绕过 ORM 直读原始列 → 必须是密文
        db = get_session()
        try:
            raw = db.execute(
                sa_text("SELECT content FROM memory_chunks WHERE user_id = :u"), {"u": uid}
            ).scalar()
            assert raw != "止损不超过2%", "content 未加密落库"
            assert "止损" not in raw
            assert crypto.decrypt_str(raw) == "止损不超过2%"
        finally:
            db.close()

        # ORM 读出 → 明文
        db = get_session()
        try:
            chunk = db.query(MemoryChunk).filter(MemoryChunk.user_id == uid).first()
            assert chunk.content == "止损不超过2%"
            # 检索返回解密原文
            hits = store.search(db, uid, "止损不超过2%", top_k=3)
            assert hits and hits[0]["content"] == "止损不超过2%"
            # 去重比对也用明文
            dup = store.find_duplicate(db, uid, "止损不超过2%")
            assert dup is not None and dup["content"] == "止损不超过2%"
        finally:
            db.close()

        # API 返回明文（不是密文）
        r = client.post("/api/v1/auth/login", json={"username": uname, "password": "pass123456"})
        token = r.json()["data"]["token"]
        r = client.get("/api/v1/memory/facts", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        items = r.json()["data"]["items"]
        assert items and items[0]["content"] == "止损不超过2%"
    finally:
        _cleanup(uid, uname, env["memory"])


def test_memory_chunk_embedding_stays_plaintext(client: TestClient, env):
    """embedding 保持明文向量（加密后无法计算相似度）。"""
    uname = _uname()
    user = _register(client, uname)
    uid = user["id"]
    try:
        db = get_session()
        try:
            row = store.add_chunk(db, uid, "v1", "止损不超过2%", {"source_type": "rule", "importance": 8})
            db.commit()
            assert row.embedding is not None
            assert len(list(row.embedding)) == 384
            assert row.embedding_kind == "hash"
        finally:
            db.close()
    finally:
        _cleanup(uid, uname, env["memory"])


def test_legacy_plaintext_content_row_still_readable(client: TestClient, env):
    """存量明文 content 行（G34 之前写入）仍可正常读出与检索。"""
    from sqlalchemy import text as sa_text

    uname = _uname()
    user = _register(client, uname)
    uid = user["id"]
    try:
        db = get_session()
        try:
            # 模拟存量行：直接用 SQL 写明文
            db.execute(
                sa_text(
                    "INSERT INTO memory_chunks (user_id, source_type, content, vector_id, importance, embedding_kind) "
                    "VALUES (:u, 'rule', '存量明文记忆', 'legacy_v1', 8, 'hash')"
                ),
                {"u": uid},
            )
            db.commit()
        finally:
            db.close()

        db = get_session()
        try:
            chunk = db.query(MemoryChunk).filter(MemoryChunk.user_id == uid, MemoryChunk.vector_id == "legacy_v1").first()
            assert chunk is not None
            assert chunk.content == "存量明文记忆", "存量明文行读取失败"
        finally:
            db.close()
    finally:
        _cleanup(uid, uname, env["memory"])

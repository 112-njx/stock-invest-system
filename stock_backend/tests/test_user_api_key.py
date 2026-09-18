"""G14（P0-2）测试：用户自填 API Key（加密存储/格式校验/优先级）+ token 用量累计。"""

import secrets
import uuid

import pytest
from app.core import crypto
from app.models.user import User
from app.repositories import user_repo
from app.services.llm import llm_service as llm_mod
from app.services.llm.llm_service import LLMService
from app.services.llm.providers.base import LLMResult
from app.services.llm.user_key import (
    ApiKeyFormatError,
    build_llm_service_for_user,
    get_user_api_key,
    validate_api_key,
)
from app.utils.db import get_session
from fastapi.testclient import TestClient
from sqlalchemy import text as sa_text

_PREFIX = "test_g14_"
_GOOD_KEY = "sk-" + "a" * 40


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    """注入随机加密密钥（用户 Key 落库加密依赖 G15 的 crypto）。"""
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


def _login(client: TestClient, username: str) -> str:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": "pass123456"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _cleanup(uid: int, uname: str) -> None:
    db = get_session()
    try:
        db.query(User).filter(User.username == uname).delete()
        db.commit()
    finally:
        db.close()


# ---- 格式校验 ----
def test_validate_api_key_accepts_wellformed():
    assert validate_api_key(_GOOD_KEY) == _GOOD_KEY
    assert validate_api_key(f"  {_GOOD_KEY}  ") == _GOOD_KEY  # 去空白


@pytest.mark.parametrize(
    "bad",
    ["", "   ", "sk-", "sk-short", "AKIA1234567890", "sk-" + "a" * 10, "sk-" + "!" * 40],
)
def test_validate_api_key_rejects_malformed(bad):
    with pytest.raises(ApiKeyFormatError):
        validate_api_key(bad)


def test_validate_api_key_rejects_overlong():
    with pytest.raises(ApiKeyFormatError):
        validate_api_key("sk-" + "a" * 200)


# ---- API：设置 / 查询 / 清除 ----
def test_set_get_and_clear_api_key(client: TestClient):
    uname = _uname()
    user = _register(client, uname)
    uid = user["id"]
    try:
        token = _login(client, uname)
        h = {"Authorization": f"Bearer {token}"}

        # 初始未配置
        r = client.get("/api/v1/users/me/api-key", headers=h)
        assert r.status_code == 200
        assert r.json()["data"]["has_api_key"] is False

        # 设置合法 key
        r = client.put("/api/v1/users/me/api-key", json={"api_key": _GOOD_KEY}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()["data"]
        assert body["has_api_key"] is True
        assert body["masked"] == f"{_GOOD_KEY[:7]}****{_GOOD_KEY[-4:]}"
        assert _GOOD_KEY not in r.text, "响应不得回显明文 Key"

        # /me 也反映已配置，且不含明文
        r = client.get("/api/v1/users/me", headers=h)
        assert r.json()["data"]["has_api_key"] is True
        assert _GOOD_KEY not in r.text

        # 非法 key → 400
        r = client.put("/api/v1/users/me/api-key", json={"api_key": "not-a-key"}, headers=h)
        assert r.status_code == 400
        assert r.json()["code"] == 40030

        # 清除
        r = client.put("/api/v1/users/me/api-key", json={"api_key": ""}, headers=h)
        assert r.status_code == 200
        assert r.json()["data"]["has_api_key"] is False
        db = get_session()
        try:
            assert get_user_api_key(db, uid) is None
        finally:
            db.close()
    finally:
        _cleanup(uid, uname)


def test_api_key_endpoints_require_auth(client: TestClient):
    assert client.get("/api/v1/users/me/api-key").status_code == 401
    assert client.put("/api/v1/users/me/api-key", json={"api_key": _GOOD_KEY}).status_code == 401


# ---- 加密存储 ----
def test_api_key_stored_encrypted(client: TestClient):
    """Key 落库为密文（直读原始列验证），ORM 读出为明文。"""
    uname = _uname()
    user = _register(client, uname)
    uid = user["id"]
    try:
        token = _login(client, uname)
        client.put("/api/v1/users/me/api-key", json={"api_key": _GOOD_KEY}, headers={"Authorization": f"Bearer {token}"})

        db = get_session()
        try:
            raw = db.execute(sa_text("SELECT api_key_encrypted FROM users WHERE id = :u"), {"u": uid}).scalar()
            assert raw and raw != _GOOD_KEY, "API Key 未加密落库"
            assert "sk-" not in raw, "密文中泄漏 Key 前缀"
            assert crypto.decrypt_str(raw) == _GOOD_KEY
            assert get_user_api_key(db, uid) == _GOOD_KEY  # ORM 解密
        finally:
            db.close()
    finally:
        _cleanup(uid, uname)


# ---- 优先级：用户 key 优先，服务端 key 兜底 ----
class _FakeProvider:
    """记录被调用时使用的 key，用于验证优先级。"""

    name = "fake"
    last_usage = (0, 0)

    def __init__(self, api_key=None):
        self.api_key = api_key

    async def ainvoke(self, messages, temperature=None):
        return LLMResult(text="ok", model="fake", tokens=3, prompt_tokens=2, completion_tokens=1)

    async def astream(self, messages, temperature=None):
        yield "ok"


def test_user_key_takes_priority_over_server_key(client: TestClient, monkeypatch):
    """填了用户 key → 装配独立 provider 使用该 key；清除后 → 复用服务端默认 provider。"""
    # llm_service 以 `from ... import DeepSeekProvider` 绑定名字，须打在 llm_mod 上
    monkeypatch.setattr(llm_mod, "DeepSeekProvider", _FakeProvider)
    monkeypatch.setattr(llm_mod, "_service", None)  # 重置单例，避免跨用例污染
    monkeypatch.setattr(llm_mod.settings, "DEEPSEEK_API_KEY", "sk-" + "s" * 40)

    uname = _uname()
    user = _register(client, uname)
    uid = user["id"]
    try:
        token = _login(client, uname)
        h = {"Authorization": f"Bearer {token}"}
        client.put("/api/v1/users/me/api-key", json={"api_key": _GOOD_KEY}, headers=h)

        db = get_session()
        try:
            svc = build_llm_service_for_user(db, uid)
            assert svc.provider.api_key == _GOOD_KEY, "应使用用户自填 key"
            assert svc.available is True
            # 派生实例共享进程级熔断/限流
            assert svc.breaker is llm_mod.get_llm_service().breaker
        finally:
            db.close()

        # 清除后 → 复用服务端默认 provider（不新建）
        client.put("/api/v1/users/me/api-key", json={"api_key": ""}, headers=h)
        db = get_session()
        try:
            svc = build_llm_service_for_user(db, uid)
            assert svc.provider is llm_mod.get_llm_service().provider, "未填 key 应回退服务端默认 provider"
            assert svc.usage_sink is not None, "无用户 key 时仍要统计用量"
        finally:
            db.close()
    finally:
        _cleanup(uid, uname)


def test_available_false_without_any_key(monkeypatch):
    monkeypatch.setattr(llm_mod.settings, "DEEPSEEK_API_KEY", "")
    svc = LLMService(provider=_FakeProvider(), api_key=None)
    assert svc.available is False
    assert LLMService(provider=_FakeProvider(), api_key=_GOOD_KEY).available is True


def test_with_api_key_shares_breaker_and_bucket():
    """派生实例共享熔断器与限流桶（保护仍是进程级），避免每个用户各有一套状态。"""
    base = LLMService(provider=_FakeProvider())
    derived = base.with_api_key(_GOOD_KEY)
    assert derived.breaker is base.breaker
    assert derived.bucket is base.bucket
    assert derived.api_key == _GOOD_KEY
    assert base.with_api_key(None) is base  # 无 key 时返回原实例


# ---- token 用量累计 ----
def test_usage_sink_accumulates_tokens(client: TestClient, monkeypatch):
    """调用完成后 token 用量累加到 users 表。"""
    monkeypatch.setattr(llm_mod.settings, "DEEPSEEK_API_KEY", "sk-" + "s" * 40)
    uname = _uname()
    user = _register(client, uname)
    uid = user["id"]
    try:
        db = get_session()
        try:
            svc = build_llm_service_for_user(db, uid)
            assert svc.usage_sink is not None
            svc.usage_sink(120, 80, False)  # 模拟一次调用上报
        finally:
            db.close()

        db = get_session()
        try:
            row = user_repo.get_by_id(db, uid)
            assert row.llm_tokens_prompt == 120
            assert row.llm_tokens_completion == 80
        finally:
            db.close()
    finally:
        _cleanup(uid, uname)


def test_add_llm_tokens_is_additive():
    """多次累加为求和，负值被夹到 0。"""
    uname = _uname()
    db = get_session()
    try:
        u = user_repo.create(db, uname, "x", f"{uname}@t.local", None)
        db.commit()
        uid = u.id
        user_repo.add_llm_tokens(db, uid, 10, 5)
        db.commit()
        user_repo.add_llm_tokens(db, uid, 20, 7)
        db.commit()
        user_repo.add_llm_tokens(db, uid, -3, -3)  # 负值不应扣减
        db.commit()
        row = user_repo.get_by_id(db, uid)
        assert row.llm_tokens_prompt == 30
        assert row.llm_tokens_completion == 12
    finally:
        db.query(User).filter(User.username == uname).delete()
        db.commit()
        db.close()


def test_me_exposes_token_totals(client: TestClient):
    """个人设置页数据源：/me 返回累计 token（含合计）。"""
    uname = _uname()
    user = _register(client, uname)
    uid = user["id"]
    try:
        db = get_session()
        try:
            user_repo.add_llm_tokens(db, uid, 100, 50)
            db.commit()
        finally:
            db.close()

        token = _login(client, uname)
        r = client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
        data = r.json()["data"]
        assert data["llm_tokens_prompt"] == 100
        assert data["llm_tokens_completion"] == 50
        assert data["llm_tokens_total"] == 150
    finally:
        _cleanup(uid, uname)


def test_usage_estimation_fallback_when_no_upstream_usage():
    """上游未返回 usage 时本地估算（标记 estimated=True），不产生 0 计数。"""
    svc = LLMService(provider=_FakeProvider())
    prompt, completion, estimated = svc._usage_of(
        LLMResult(text="", model="m"), [{"role": "user", "content": "止损不超过2%"}], "这是回复"
    )
    assert prompt > 0 and completion > 0
    assert estimated is True

    # 上游有 usage 时不估算
    prompt2, completion2, estimated2 = svc._usage_of(
        LLMResult(text="", model="m", prompt_tokens=11, completion_tokens=7), [], ""
    )
    assert (prompt2, completion2, estimated2) == (11, 7, False)

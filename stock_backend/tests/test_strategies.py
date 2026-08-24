"""3.5 策略生成 + 3.6 交易策略 CRUD 测试。"""

import types
import uuid

import pytest
from app.agent import strategy_gen
from app.models.user import User
from app.schemas.strategy import StrategyOutput, StrategyParams
from app.services.llm import LLMError
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_str_"


class SimpleBreaker:
    def on_success(self):
        pass

    def on_failure(self):
        pass


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


_GOOD_CODE = '''def initialize(context):
    context.params["fast"] = 5

def on_bar(bar, context):
    if bar["close"] > context.params["fast"]:
        context.buy(100)
'''


def _make_output(**overrides) -> StrategyOutput:
    data = {
        "strategy_name": "双均线策略",
        "description": "金叉买入死叉卖出",
        "code": _GOOD_CODE,
        "params": StrategyParams(entry={"fast": 5, "slow": 20}),
        "risk_warning": "震荡市可能反复止损",
    }
    data.update(overrides)
    return StrategyOutput(**data)


# ---- 8.4：生成失败自动重试 ----
class _RetryStructured:
    """第 1 次返回语法错误代码，第 2 次返回合法代码。"""

    def __init__(self, bad: StrategyOutput, good: StrategyOutput):
        self.bad = bad
        self.good = good
        self.calls = 0
        self.messages_seen: list[list[dict]] = []

    async def ainvoke(self, messages):
        self.calls += 1
        self.messages_seen.append(messages)
        if self.calls == 1:
            return self.bad
        return self.good


def _make_bad_output() -> StrategyOutput:
    return _make_output(code="def on_bar(bar, context):\n  x = ")  # 语法错误


async def test_generate_strategy_retries_on_validation_failure():
    good = _make_output()
    bad = _make_bad_output()
    fake = _RetryStructured(bad, good)

    async def _preflight():
        pass

    fake_svc = types.SimpleNamespace(
        available=True,
        breaker=SimpleBreaker(),
        provider=types.SimpleNamespace(raw_model=None),
        preflight=_preflight,
    )

    result = await strategy_gen.generate_strategy("双均线", llm_svc=fake_svc, structured_model=fake)
    assert result.strategy_name == "双均线策略"  # 重试后成功
    assert fake.calls == 2
    # 重试 prompt 应包含校验错误信息（拼回错误要求修复）
    assert "校验错误" in fake.messages_seen[-1][-1]["content"]


class _AlwaysBadStructured:
    async def ainvoke(self, messages):
        return _make_bad_output()


async def test_generate_strategy_exhausted_retries_raises():
    async def _preflight():
        pass

    fake_svc = types.SimpleNamespace(
        available=True,
        breaker=SimpleBreaker(),
        provider=types.SimpleNamespace(raw_model=None),
        preflight=_preflight,
    )
    with pytest.raises(LLMError) as exc_info:
        await strategy_gen.generate_strategy("双均线", llm_svc=fake_svc, structured_model=_AlwaysBadStructured())
    assert "基于模板创建" in str(exc_info.value)


# ---- 3.5 单元：generate_strategy（注入结构化模型）----
async def test_generate_strategy_success():
    out = _make_output()

    async def _preflight():
        pass

    fake_svc = types.SimpleNamespace(
        available=True,
        breaker=SimpleBreaker(),
        provider=types.SimpleNamespace(raw_model=None),
        preflight=_preflight,
    )

    class FakeStructured:
        def __init__(self, value):
            self.value = value

        async def ainvoke(self, messages):
            return self.value

    result = await strategy_gen.generate_strategy("双均线", llm_svc=fake_svc, structured_model=FakeStructured(out))
    assert result.strategy_name == "双均线策略"
    assert result.params.entry == {"fast": 5, "slow": 20}


async def test_generate_strategy_unavailable():
    fake_svc = types.SimpleNamespace(available=False)
    with pytest.raises(LLMError):
        await strategy_gen.generate_strategy("描述", llm_svc=fake_svc, structured_model=None)


# ---- 3.5 API ----
def test_generate_api(client: TestClient, monkeypatch):
    uname = _uname()
    try:
        out = _make_output()

        async def _fake(description, llm_svc=None, structured_model=None):
            return out

        monkeypatch.setattr(strategy_gen, "generate_strategy", _fake)
        token = _register(client, uname)
        resp = client.post(
            "/api/v1/strategies/generate",
            json={"description": "双均线策略"},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["strategy_name"] == "双均线策略"
        assert data["params"]["entry"] == {"fast": 5, "slow": 20}

        assert client.post("/api/v1/strategies/generate", json={"description": "x"}).status_code == 401
    finally:
        _cleanup_users(uname)


# ---- 3.6 CRUD ----
def test_strategy_crud(client: TestClient):
    uname = _uname()
    try:
        token = _register(client, uname)
        h = _auth(token)

        r = client.post(
            "/api/v1/strategies",
            json={"title": "双均线", "description": "金叉买死叉卖", "code": _GOOD_CODE, "params": {"entry": {"fast": 5}}, "status": "active"},
            headers=h,
        )
        assert r.status_code == 200 and r.json()["code"] == 0
        sid = r.json()["data"]["id"]

        # 列表
        rows = client.get("/api/v1/strategies", headers=h).json()["data"]
        assert any(s["id"] == sid for s in rows)

        # 详情
        detail = client.get(f"/api/v1/strategies/{sid}", headers=h).json()["data"]
        assert detail["title"] == "双均线"

        # 更新
        r = client.put(f"/api/v1/strategies/{sid}", json={"status": "draft", "params": {"entry": {"fast": 10}}}, headers=h)
        assert r.json()["data"]["status"] == "draft"
        assert r.json()["data"]["params"]["entry"] == {"fast": 10}

        # 删除
        assert client.delete(f"/api/v1/strategies/{sid}", headers=h).json()["code"] == 0
        assert client.get(f"/api/v1/strategies/{sid}", headers=h).status_code == 404
    finally:
        _cleanup_users(uname)


def test_strategy_ownership(client: TestClient):
    uname1, uname2 = _uname(), _uname()
    try:
        t1 = _register(client, uname1)
        t2 = _register(client, uname2)
        sid = client.post("/api/v1/strategies", json={"title": "私密策略"}, headers=_auth(t1)).json()["data"]["id"]
        assert client.get(f"/api/v1/strategies/{sid}", headers=_auth(t2)).status_code == 404
        assert client.put(f"/api/v1/strategies/{sid}", json={"title": "hack"}, headers=_auth(t2)).status_code == 404
        assert client.delete(f"/api/v1/strategies/{sid}", headers=_auth(t2)).status_code == 404
    finally:
        _cleanup_users(uname1, uname2)

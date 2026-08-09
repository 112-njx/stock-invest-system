"""3.7 用户定制 Agent CRUD + 会话选用集成测试。"""

import types
import uuid

from app.agent import chat_service
from app.models.user import User
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_ag_"


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _register(client: TestClient, username: str) -> dict:
    r = client.post("/api/v1/auth/register", json={"username": username, "password": "pass123456"})
    assert r.status_code == 200, r.text
    return r.json()["data"]


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


def test_agent_crud_and_preset(client: TestClient):
    uname = _uname()
    try:
        user = _register(client, uname)
        token = user["token"]
        h = _auth(token)

        # 从模板创建（未传 system_prompt → 使用预设）
        r = client.post(
            "/api/v1/agents", json={"name": "我的风控", "template": "risk_control"}, headers=h
        )
        assert r.status_code == 200
        data = r.json()["data"]
        aid = data["id"]
        assert "风控" in data["system_prompt"]
        assert data["llm_config"]["temperature"] == 0.2

        # 列表
        rows = client.get("/api/v1/agents", headers=h).json()["data"]
        assert any(a["id"] == aid for a in rows)

        # 详情
        assert client.get(f"/api/v1/agents/{aid}", headers=h).json()["data"]["name"] == "我的风控"

        # 启停更新（draft→active）
        r = client.patch(f"/api/v1/agents/{aid}", json={"status": "active"}, headers=h)
        assert r.json()["data"]["status"] == "active"

        # 删除
        assert client.delete(f"/api/v1/agents/{aid}", headers=h).json()["code"] == 0
        assert client.get(f"/api/v1/agents/{aid}", headers=h).status_code == 404
    finally:
        _cleanup_users(uname)


def test_agent_ownership(client: TestClient):
    uname1, uname2 = _uname(), _uname()
    try:
        t1 = _register(client, uname1)["token"]
        t2 = _register(client, uname2)["token"]
        aid = client.post("/api/v1/agents", json={"name": "私密Agent"}, headers=_auth(t1)).json()["data"]["id"]
        assert client.get(f"/api/v1/agents/{aid}", headers=_auth(t2)).status_code == 404
        assert client.patch(f"/api/v1/agents/{aid}", json={"status": "active"}, headers=_auth(t2)).status_code == 404
        assert client.delete(f"/api/v1/agents/{aid}", headers=_auth(t2)).status_code == 404
    finally:
        _cleanup_users(uname1, uname2)


def test_agent_requires_token(client: TestClient):
    assert client.get("/api/v1/agents").status_code == 401
    assert client.post("/api/v1/agents", json={"name": "x"}).status_code == 401


# ---- 会话选用定制 Agent：system_prompt 生效 ----
from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from pydantic import Field  # noqa: E402


class _CaptureModel(BaseChatModel):
    """BaseChatModel 假模型：捕获 messages，返回固定文本（兼容 create_agent 工具绑定）。"""

    captured: list = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _should_stream(self, **kwargs) -> bool:
        return False

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.captured.append(messages)
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="按我的交易体系分析"))])


class _FakeLLM:
    available = True

    def __init__(self, model):
        self.model = model
        self.provider = types.SimpleNamespace(raw_model=model)
        self.breaker = types.SimpleNamespace(on_success=lambda: None, on_failure=lambda: None)

    async def preflight(self):
        pass


def test_chat_uses_custom_agent_system_prompt(client: TestClient):
    uname = _uname()
    try:
        user = _register(client, uname)
        token = user["token"]
        h = _auth(token)

        agent = client.post(
            "/api/v1/agents",
            json={"name": "定制", "system_prompt": "你是我的专属交易教练，只做波段不追高"},
            headers=h,
        ).json()["data"]
        conv = client.post("/api/v1/conversations", json={}, headers=h).json()["data"]

        model = _CaptureModel()
        events = []

        async def _run():
            async for ev in chat_service.stream_chat(
                user_id=user["user"]["id"],
                conversation_id=conv["id"],
                symbol=None,
                content="分析下我的仓位",
                agent_id=agent["id"],
                run_type="custom",
                llm_svc=_FakeLLM(model),
                model=model,
            ):
                events.append(ev)

        import asyncio

        asyncio.run(_run())
        assert any(e["type"] == "delta" for e in events)
        # 注入 LLM 的首条 system 消息包含定制 prompt
        assert model.captured, "model 应被调用"
        system_msg = model.captured[0][0]
        assert getattr(system_msg, "type", None) == "system"
        assert "专属交易教练" in system_msg.content
    finally:
        _cleanup_users(uname)

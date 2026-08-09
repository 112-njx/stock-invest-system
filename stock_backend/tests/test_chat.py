"""3.3 工具集+上下文+流式对话测试：上下文组装、SSE 事件、消息/run 落库、LLM 不可用降级、工具调用。"""

import types
import uuid

from app.agent import chat_service
from app.agent.context import build_llm_messages, build_tools
from app.agent.prompts import build_system_prompt
from app.models.agent import AgentRun, AgentStep
from app.models.symbol import Symbol
from app.models.user import User
from app.utils.db import get_session
from fastapi.testclient import TestClient
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

_PREFIX = "test_chat_"


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


def _seed_symbol() -> tuple[int, str]:
    """创建唯一测试标的（随机代码+名称，避免与真实数据冲突/误删）。"""
    code = f"9{uuid.uuid4().hex[:5]}"
    name = f"聊天测试{uuid.uuid4().hex[:6]}"
    db = get_session()
    sym = Symbol(code=code, name=name, type="stock", market="SSE")
    db.add(sym)
    db.commit()
    db.refresh(sym)
    sid = sym.id
    db.close()
    return sid, code


def _cleanup_symbol(code: str) -> None:
    db = get_session()
    try:
        sym = db.query(Symbol).filter(Symbol.code == code).first()
        if sym:
            db.delete(sym)
        db.commit()
    finally:
        db.close()


def _cleanup_agent_run(run_id: int) -> None:
    db = get_session()
    try:
        db.query(AgentStep).filter(AgentStep.run_id == run_id).delete()
        db.query(AgentRun).filter(AgentRun.id == run_id).delete()
        db.commit()
    finally:
        db.close()


# ---- 假 ChatModel / LLMService ----
class FakeChatModel(BaseChatModel):
    """按调用次数返回：第1次工具调用、后续最终文本。with_tool=False 直接返回最终文本。"""

    with_tool: bool = False
    final_text: str = "分析完成"
    tool_symbol: str = "600519"
    invokes: int = 0

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _should_stream(self, **kwargs) -> bool:
        return False

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.invokes += 1
        if self.with_tool and self.invokes == 1:
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "market_snapshot",
                                    "args": {"symbol": self.tool_symbol},
                                    "id": "call_1",
                                    "type": "tool_call",
                                }
                            ],
                        )
                    )
                ]
            )
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.final_text))])


class FakeBreaker:
    def __init__(self):
        self.open = False

    def on_success(self):
        self.open = False

    def on_failure(self):
        self.open = True


class FakeLLMService:
    def __init__(self, model, available: bool = True):
        self.model = model
        self.available = available
        self.breaker = FakeBreaker()
        self.provider = types.SimpleNamespace(raw_model=model)

    async def preflight(self):
        pass


# ---- 单元：上下文组装 ----
def test_build_system_prompt_has_rules():
    sp = build_system_prompt()
    assert "禁止编造" in sp
    assert "不构成投资建议" in sp
    sp2 = build_system_prompt(extra_rules="只做波段")
    assert "只做波段" in sp2


def test_build_llm_messages_order():
    msgs = build_llm_messages(
        system_prompt="SYS", history=[{"role": "user", "content": "h1"}], user_content="q", memory_context="记忆A"
    )
    assert msgs[0]["role"] == "system" and msgs[0]["content"] == "SYS"
    assert "记忆A" in msgs[1]["content"]
    assert msgs[2] == {"role": "user", "content": "h1"}
    assert msgs[3] == {"role": "user", "content": "q"}


def test_build_tools_return_market_indicator():
    db = get_session()
    try:
        tools = build_tools(db)
        names = [getattr(t, "name", "") or t.__class__.__name__ for t in tools]
        assert "market_snapshot" in names
        assert "get_kline" in names
        assert "get_indicator" in names
    finally:
        db.close()


# ---- 单元：stream_chat 主流程 ----
def _run_stream_chat(fake_svc, **kwargs):
    events = []

    async def _collect():
        async for ev in chat_service.stream_chat(**kwargs, llm_svc=fake_svc, model=fake_svc.model):
            events.append(ev)

    import asyncio

    asyncio.run(_collect())
    return events


def test_stream_chat_fallback_when_unavailable(client: TestClient):
    uname = _uname()
    try:
        token = _register(client, uname)
        me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]
        fake = FakeLLMService(FakeChatModel(), available=False)
        events = _run_stream_chat(fake, user_id=me["id"], conversation_id=None, symbol=None, content="hi", run_type="custom")
        assert events[0]["type"] == "start"
        assert any(e["type"] == "delta" and "不可用" in e["content"] for e in events)
        assert events[-1]["type"] == "done"
    finally:
        _cleanup_users(uname)


def test_stream_chat_success_saves_messages_and_run(client: TestClient):
    uname = _uname()
    sid, code = _seed_symbol()
    try:
        token = _register(client, uname)
        # 建会话 + 取 user_id
        conv = client.post("/api/v1/conversations", json={}, headers=_auth(token)).json()["data"]
        me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]
        fake = FakeLLMService(FakeChatModel(final_text="深度分析结果"))
        events = _run_stream_chat(
            fake, user_id=me["id"], conversation_id=conv["id"], symbol=code, content="分析这只股", run_type="custom"
        )
        assert events[0]["type"] == "start"
        deltas = [e["content"] for e in events if e["type"] == "delta"]
        assert any("分析结果" in d for d in deltas)
        done = events[-1]
        assert done["type"] == "done" and done["conversation_id"] == conv["id"]
        assert fake.breaker.open is False

        # 会话中应存在 user + assistant 两条消息，且 assistant 绑定标的
        msgs = client.get(f"/api/v1/conversations/{conv['id']}/messages", headers=_auth(token)).json()["data"]
        roles = [m["role"] for m in msgs]
        assert roles == ["user", "assistant"]
        assert msgs[-1]["symbol_id"] == sid
        assert msgs[-1]["content"] == "深度分析结果"

        # agent_run 已落库（success）
        db = get_session()
        try:
            run = db.query(AgentRun).filter(AgentRun.conversation_id == conv["id"]).first()
            assert run is not None and run.status == "success"
            assert run.run_type == "custom"
            _cleanup_agent_run(run.id)
        finally:
            db.close()
    finally:
        _cleanup_symbol(code)
        _cleanup_users(uname)


def test_stream_chat_tool_call_records_steps(client: TestClient):
    uname = _uname()
    _sid, code = _seed_symbol()
    try:
        token = _register(client, uname)
        conv = client.post("/api/v1/conversations", json={}, headers=_auth(token)).json()["data"]
        me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]
        fake = FakeLLMService(FakeChatModel(with_tool=True, final_text="基于快照给出结论", tool_symbol=code))
        events = _run_stream_chat(fake, user_id=me["id"], conversation_id=conv["id"], symbol=code, content="看下行情", run_type="custom")
        tool_events = [e for e in events if e["type"] == "tool_call"]
        assert tool_events and tool_events[0]["tool"] == "market_snapshot"

        db = get_session()
        try:
            run = db.query(AgentRun).filter(AgentRun.conversation_id == conv["id"]).first()
            steps = db.query(AgentStep).filter(AgentStep.run_id == run.id).all()
            assert any(s.step_name.startswith("tool:") for s in steps)  # 工具调用步骤已记录
            assert any(s.step_name.startswith("tool_result:") for s in steps)
            _cleanup_agent_run(run.id)
        finally:
            db.close()
    finally:
        _cleanup_symbol(code)
        _cleanup_users(uname)


# ---- API：SSE 降级 ----
def test_chat_api_stream_and_requires_token(client: TestClient, monkeypatch):
    uname = _uname()
    try:
        from app.agent import chat_service as cs

        fake = FakeLLMService(FakeChatModel(), available=False)
        monkeypatch.setattr(cs, "get_llm_service", lambda: fake)

        token = _register(client, uname)
        resp = client.post("/api/v1/chat", json={"content": "你好"}, headers=_auth(token))
        assert resp.status_code == 200
        body = resp.text
        assert "data: " in body
        assert "不可用" in body

        assert client.post("/api/v1/chat", json={"content": "x"}).status_code == 401
    finally:
        _cleanup_users(uname)

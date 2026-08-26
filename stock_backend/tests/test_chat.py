"""3.3 工具集+上下文+流式对话测试：上下文组装、SSE 事件、消息/run 落库、LLM 不可用降级、工具调用。"""

import types
import uuid

from app.agent import chat_service
from app.agent.context import build_llm_messages, build_tools
from app.agent.prompts import build_system_prompt
from app.models.agent import AgentRun, AgentStep
from app.models.symbol import Symbol
from app.models.user import User
from app.repositories import conversation_repo
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


def test_stream_chat_model_none_with_available_not_fallback(client: TestClient):
    """回归：API 实际调用不传 model（model=None）且 llm 可用时，不得因 model is None 走降级。"""
    import asyncio

    uname = _uname()
    _sid, code = _seed_symbol()
    try:
        token = _register(client, uname)
        conv = client.post("/api/v1/conversations", json={}, headers=_auth(token)).json()["data"]
        me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]
        fake = FakeLLMService(FakeChatModel(final_text="可用模型正常分析"))
        events: list[dict] = []

        async def _collect():
            # 不传 model → model=None，但 llm_svc.available=True → 必须走正常 Agent 流而非降级
            async for ev in chat_service.stream_chat(
                user_id=me["id"], conversation_id=conv["id"], symbol=code, content="测试", run_type="custom", llm_svc=fake
            ):
                events.append(ev)

        asyncio.run(_collect())
        deltas = [e["content"] for e in events if e["type"] == "delta"]
        assert not any("不可用" in d for d in deltas)  # 未走降级文案
        assert any("正常分析" in d for d in deltas)
        assert events[-1]["type"] == "done"
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


# ---- 5.1：SSE 心跳与超时保护 ----
def test_stream_with_timeouts_truncates_on_stall(monkeypatch):
    """首字超时：gen 不产出 → 返回 truncated done + 保存部分内容（status=failed/error=timeout）。"""
    import asyncio

    from app.agent import chat_service as cs

    monkeypatch.setattr(cs.settings, "SSE_FIRST_TOKEN_TIMEOUT", 0.01)
    monkeypatch.setattr(cs.settings, "SSE_TOTAL_TIMEOUT", 30.0)
    saved = {}
    monkeypatch.setattr(
        cs,
        "_save_result",
        lambda db, run, user_msg, conv, symbol_id, text, tokens, status, error=None: saved.update(
            status=status, error=error, text=text
        )
        or types.SimpleNamespace(id=1),
    )

    class _Conv:
        id = 5

    class _Run:
        id = 9
        user_id = 1

    async def _gen():
        await asyncio.sleep(10)  # 挂起不产出
        yield {"type": "done"}

    async def _collect():
        evs = []
        async for ev in cs._stream_with_timeouts(_gen(), None, _Run(), None, _Conv(), None):
            evs.append(ev)
        return evs

    evs = asyncio.run(_collect())
    assert evs[-1]["type"] == "done"
    assert evs[-1]["truncated"] is True
    assert evs[-1]["reason"] == "timeout"
    assert saved["status"] == "failed"
    assert saved["error"] == "timeout"


def test_stream_with_timeouts_passthrough():
    """正常路径：delta 加 seq 并透传，done 透传，不注入 truncated。"""
    import asyncio

    from app.agent import chat_service as cs

    class _Conv:
        id = 12345

    async def _gen():
        yield {"type": "delta", "content": "你好"}
        yield {"type": "done", "message_id": 1}

    async def _collect():
        return [ev async for ev in cs._stream_with_timeouts(_gen(), None, None, None, _Conv(), None)]

    evs = asyncio.run(_collect())
    assert evs[0] == {"type": "delta", "content": "你好", "seq": 1}
    assert evs[1] == {"type": "done", "message_id": 1}


def test_sse_keepalive_emits(monkeypatch):
    """空闲时发送 :keepalive 注释行，同时透传 data 帧。"""
    import asyncio

    from app.api.v1 import chat as chat_api

    monkeypatch.setattr(chat_api.settings, "SSE_KEEPALIVE_INTERVAL", 0.02)

    async def _gen():
        await asyncio.sleep(0.06)
        yield {"type": "done"}

    async def _collect():
        frames = []
        async for f in chat_api._sse_keepalive(_gen()):
            frames.append(f)
        return frames

    frames = asyncio.run(_collect())
    assert any(":keepalive" in f for f in frames)
    assert any(f.startswith("data: ") and "done" in f for f in frames)


# ---- 5.3：错误帧标准化 ----
class FakeErrorChatModel(FakeChatModel):
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise ConnectionError("network down")


def test_stream_chat_error_frame_standardized(client: TestClient):
    """LLM 失败 → 标准化 error 帧（code/retryable/message），而非旧 content 格式。"""
    uname = _uname()
    try:
        token = _register(client, uname)
        me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]
        fake = FakeLLMService(FakeErrorChatModel())
        events = _run_stream_chat(fake, user_id=me["id"], conversation_id=None, symbol=None, content="hi", run_type="custom")
        errs = [e for e in events if e["type"] == "error"]
        assert errs, f"期望 error 事件，实际 {[e['type'] for e in events]}"
        err = errs[0]
        assert err["code"] == "NETWORK_ERROR"
        assert err["retryable"] is True
        assert "message" in err and err["message"]
    finally:
        _cleanup_users(uname)


# ---- 6.4：记忆写入反馈 memory_saved 事件 ----
def test_stream_chat_emits_memory_saved(client: TestClient, monkeypatch):
    from app.agent.memory import memory_service as ms

    facts = [{"content": "止损不超过2%", "type": "rule", "importance": 7}]

    async def _fake_extract(user_msg, assistant_msg, llm_svc=None):
        return facts

    monkeypatch.setattr(ms, "aextract_facts", _fake_extract)
    monkeypatch.setattr(ms, "save_memory", lambda *a, **k: 1)  # 隔离真实 chroma/文件写入

    uname = _uname()
    try:
        token = _register(client, uname)
        me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]
        fake = FakeLLMService(FakeChatModel(final_text="分析完成"))
        events = _run_stream_chat(fake, user_id=me["id"], conversation_id=None, symbol=None, content="hi", run_type="custom")
        mem_evs = [e for e in events if e["type"] == "memory_saved"]
        assert mem_evs, f"期望 memory_saved 事件，实际 {[e['type'] for e in events]}"
        assert mem_evs[0]["summary"] == "止损不超过2%"
        assert mem_evs[0]["importance"] == 7
        assert events[-1]["type"] == "done"  # memory_saved 在 done 之前
    finally:
        _cleanup_users(uname)


# ---- 5.4：错误分级降级 ----
def test_rule_based_analysis_format(monkeypatch):
    from app.agent import chat_service as cs

    fake_rows = [{"macd_dif": 1.0, "macd_dea": 0.5, "kdj_k": 85, "kdj_d": 80}]
    monkeypatch.setattr(cs.indicator_service, "compute_indicators", lambda *a, **k: fake_rows)
    text = cs._rule_based_analysis(None, 1)
    assert "MACD金叉" in text
    assert "KDJ超买" in text
    assert "偏多" in text


def test_rule_based_analysis_no_symbol():
    from app.agent import chat_service as cs

    assert "未绑定分析标的" in cs._rule_based_analysis(None, None)


def test_degraded_text_token_error():
    from app.agent import chat_service as cs

    assert cs._degraded_text(None, None, "TOKEN_INVALID") == "您的DeepSeek API Key无效或余额不足，请检查配置"
    assert cs._degraded_text(None, None, "TOKEN_QUOTA") == "您的DeepSeek API Key无效或余额不足，请检查配置"


def test_degraded_text_circuit_open_uses_rule_based():
    from app.agent import chat_service as cs

    assert "已切换基础分析模式" in cs._degraded_text(None, 1, "PROVIDER_UNAVAILABLE")


def test_yield_failure_circuit_open_saves_rule_text(monkeypatch):
    from app.agent import chat_service as cs
    from app.services.llm.llm_service import LLMCircuitOpenError

    saved = {}
    monkeypatch.setattr(
        cs,
        "_save_result",
        lambda db, run, u, c, sid, text, t, s, e=None: saved.update(text=text, error=e) or types.SimpleNamespace(id=1),
    )
    monkeypatch.setattr(cs.indicator_service, "compute_indicators", lambda *a, **k: [{"macd_dif": 1.0, "macd_dea": 0.5, "kdj_k": 85, "kdj_d": 80}])

    class _Conv:
        id = 1

    class _Run:
        id = 2

    ev = cs._yield_failure(None, _Run(), None, _Conv(), 1, LLMCircuitOpenError("熔断"))
    assert ev["code"] == "PROVIDER_UNAVAILABLE"
    assert "已切换基础分析模式" in saved["text"]
    assert "MACD金叉" in saved["text"]


def test_build_system_prompt_has_tool_failure_annotation():
    from app.agent.prompts import build_system_prompt

    sp = build_system_prompt()
    assert "行情数据暂时不可用，以下分析基于历史数据" in sp


# ---- 8.1：滑动窗口与摘要压缩 ----
def test_assemble_history_with_and_without_summary():
    from app.agent import chat_service as cs

    all_msgs = [{"role": "user", "content": f"m{i}"} for i in range(25)]
    # 无摘要：只取最近 MAX_HISTORY 条
    hist = cs._assemble_history(all_msgs, None)
    assert len(hist) == cs.MAX_HISTORY
    assert hist[0]["content"] == "m5"  # 25 - 20 = 5

    # 有摘要：前置 system 摘要 + 最近 MAX_HISTORY 条
    hist = cs._assemble_history(all_msgs, "用户偏好短线")
    assert hist[0] == {"role": "system", "content": "之前对话摘要：用户偏好短线"}
    assert len(hist) == cs.MAX_HISTORY + 1


class _SummaryLLM:
    available = True

    async def ainvoke(self, messages):
        return types.SimpleNamespace(text="用户偏好短线，讨论过贵州茅台")


def test_generate_conversation_summary_updates_db(client: TestClient):
    uname = _uname()
    try:
        token = _register(client, uname)
        conv = client.post("/api/v1/conversations", json={}, headers=_auth(token)).json()["data"]
        me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]

        db = get_session()
        try:
            # 造 25 条消息（> MAX_HISTORY=20），摘要应只取早期 5 条
            for i in range(25):
                conversation_repo.add_message(db, conv["id"], "user" if i % 2 == 0 else "assistant", f"msg{i}")
            db.commit()
        finally:
            db.close()

        import asyncio

        asyncio.run(chat_service._generate_conversation_summary(conv["id"], _SummaryLLM()))

        db = get_session()
        try:
            c = conversation_repo.get_conversation(db, me["id"], conv["id"])
            assert c is not None
            assert c.summary == "用户偏好短线，讨论过贵州茅台"
        finally:
            db.close()
    finally:
        _cleanup_users(uname)


# ---- 8.2：token 预算 + usage 事件 ----
def test_stream_chat_emits_usage_event(client: TestClient):
    uname = _uname()
    try:
        token = _register(client, uname)
        me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]
        fake = FakeLLMService(FakeChatModel(final_text="分析完成"))
        events = _run_stream_chat(fake, user_id=me["id"], conversation_id=None, symbol=None, content="hi", run_type="custom")
        usage = [e for e in events if e["type"] == "usage"]
        assert usage, f"期望 usage 事件，实际 {[e['type'] for e in events]}"
        assert usage[0]["prompt"] > 0
        assert usage[0]["completion"] > 0
        assert usage[0]["total"] == usage[0]["prompt"] + usage[0]["completion"]
        assert events[-1]["type"] == "done"
        assert events[-2]["type"] == "usage"  # usage 在 done 之前
    finally:
        _cleanup_users(uname)


# ---- 8.6：生成→回测一键流程（strategy 分支）----
def test_stream_chat_strategy_branch_saves_and_emits_ready(client: TestClient, monkeypatch):
    from app.agent import chat_service as cs
    from app.schemas.strategy import StrategyOutput, StrategyParams

    out = StrategyOutput(
        strategy_name="双均线策略",
        description="金叉买死叉卖",
        code="def initialize(context):\n    context.params['fast'] = 5\n\ndef on_bar(bar, context):\n    if bar['close'] > context.params['fast']:\n        context.buy(100)\n",
        params=StrategyParams(entry={"fast": 5, "slow": 20}),
        risk_warning="震荡市可能反复止损",
    )

    async def _fake_gen(description, llm_svc=None, structured_model=None):
        return out

    monkeypatch.setattr(cs, "generate_strategy", _fake_gen)

    uname = _uname()
    try:
        token = _register(client, uname)
        me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]
        fake = FakeLLMService(FakeChatModel(), available=True)
        events = _run_stream_chat(fake, user_id=me["id"], conversation_id=None, symbol=None, content="双均线策略", run_type="strategy")
        sr = [e for e in events if e["type"] == "strategy_ready"]
        assert sr, f"期望 strategy_ready，实际 {[e['type'] for e in events]}"
        assert sr[0]["strategy_id"] > 0
        assert sr[0]["auto_backtest"] is True
        assert events[-1]["type"] == "done"
        # 策略已保存，可立即用于回测（id 有效）
        rows = client.get("/api/v1/strategies", headers=_auth(token)).json()["data"]
        assert any(s["id"] == sr[0]["strategy_id"] and s["title"] == "双均线策略" for s in rows)
    finally:
        _cleanup_users(uname)


def test_stream_chat_strategy_branch_failure_hint(client: TestClient, monkeypatch):
    from app.agent import chat_service as cs
    from app.services.llm import LLMError

    async def _fake_gen(description, llm_svc=None, structured_model=None):
        raise LLMError("策略生成遇到问题，请尝试调整描述或基于模板创建。")

    monkeypatch.setattr(cs, "generate_strategy", _fake_gen)

    uname = _uname()
    try:
        token = _register(client, uname)
        me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]
        fake = FakeLLMService(FakeChatModel(), available=True)
        events = _run_stream_chat(fake, user_id=me["id"], conversation_id=None, symbol=None, content="生成策略", run_type="strategy")
        deltas = [e["content"] for e in events if e["type"] == "delta"]
        assert any("基于模板创建" in d for d in deltas)
        assert events[-1]["type"] == "done"
    finally:
        _cleanup_users(uname)


# ---- 8.7：会话标题自动生成 ----
def test_stream_chat_generates_title_on_first_message(client: TestClient, monkeypatch):
    from app.agent import chat_service as cs

    async def _fake_title(conv_id, first_msg, llm_svc, queue=None):
        db = get_session()
        try:
            conversation_repo.update_title(db, conv_id, "贵州茅台分析")
            db.commit()
        finally:
            db.close()
        if queue is not None:
            await queue.put(("title", {"type": "title", "title": "贵州茅台分析", "conversation_id": conv_id}))
        return "贵州茅台分析"

    monkeypatch.setattr(cs, "_generate_conversation_title", _fake_title)

    uname = _uname()
    try:
        token = _register(client, uname)
        me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]
        fake = FakeLLMService(FakeChatModel(final_text="分析完成"), available=True)
        events = _run_stream_chat(fake, user_id=me["id"], conversation_id=None, symbol=None, content="分析贵州茅台", run_type="custom")
        title_evs = [e for e in events if e["type"] == "title"]
        assert title_evs, f"期望 title 事件，实际 {[e['type'] for e in events]}"
        assert title_evs[0]["title"] == "贵州茅台分析"
        assert events[-1]["type"] == "title"  # title 在 done 之后
        # DB 标题已更新
        convs = client.get("/api/v1/conversations", headers=_auth(token)).json()["data"]
        assert any(c["title"] == "贵州茅台分析" for c in convs)
    finally:
        _cleanup_users(uname)


def test_stream_chat_no_title_on_followup_message(client: TestClient, monkeypatch):
    from app.agent import chat_service as cs

    called = []

    async def _fake_title(conv_id, first_msg, llm_svc, queue=None):
        called.append(conv_id)
        if queue is not None:
            await queue.put(("title", None))
        return None

    monkeypatch.setattr(cs, "_generate_conversation_title", _fake_title)

    uname = _uname()
    try:
        token = _register(client, uname)
        me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]
        fake = FakeLLMService(FakeChatModel(final_text="分析完成"), available=True)
        # 第一条消息（新建会话）
        conv = client.post("/api/v1/conversations", json={}, headers=_auth(token)).json()["data"]
        _run_stream_chat(fake, user_id=me["id"], conversation_id=conv["id"], symbol=None, content="第一条消息", run_type="custom")
        # 第二条消息（同会话，非首条）——不触发标题
        _run_stream_chat(fake, user_id=me["id"], conversation_id=conv["id"], symbol=None, content="第二条消息", run_type="custom")
        assert len(called) == 1  # 仅首条触发
    finally:
        _cleanup_users(uname)


# ---- 修复：非深度路径也写入 agent_runs.duration_ms ----
def test_stream_chat_non_deep_writes_duration(client: TestClient):
    """ReAct（custom）路径运行结束后 agent_runs.duration_ms 非空。"""
    uname = _uname()
    try:
        token = _register(client, uname)
        conv = client.post("/api/v1/conversations", json={}, headers=_auth(token)).json()["data"]
        me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]
        fake = FakeLLMService(FakeChatModel(final_text="普通分析结果"))
        _run_stream_chat(fake, user_id=me["id"], conversation_id=conv["id"], symbol=None, content="分析", run_type="custom")
        db = get_session()
        try:
            run = db.query(AgentRun).filter(AgentRun.conversation_id == conv["id"]).first()
            assert run is not None and run.status == "success"
            assert run.duration_ms is not None and run.duration_ms >= 0
        finally:
            db.close()
    finally:
        _cleanup_users(uname)


def test_stream_chat_failure_writes_duration(client: TestClient):
    """失败路径（LLM 异常）运行结束后 agent_runs.duration_ms 非空。"""
    uname = _uname()
    try:
        token = _register(client, uname)
        me = client.get("/api/v1/users/me", headers=_auth(token)).json()["data"]
        fake = FakeLLMService(FakeErrorChatModel(), available=True)
        events = _run_stream_chat(fake, user_id=me["id"], conversation_id=None, symbol=None, content="hi", run_type="custom")
        assert any(e["type"] == "error" for e in events)
        db = get_session()
        try:
            run = db.query(AgentRun).order_by(AgentRun.id.desc()).first()
            assert run is not None and run.status == "failed"
            assert run.duration_ms is not None and run.duration_ms >= 0
        finally:
            db.close()
    finally:
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

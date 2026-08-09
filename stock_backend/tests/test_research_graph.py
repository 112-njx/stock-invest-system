"""3.8 多智能体编排（LangGraph 研究图）测试：各节点输出顺序 + 深度聊天集成落库 agent_steps。"""

import types
import uuid

from app.agent import chat_service
from app.agent.research_graph import NODE_FIELD, build_research_graph, run_research_graph
from app.models.agent import AgentRun, AgentStep
from app.models.user import User
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_rg_"


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


# ---- 假模型：按角色返回对应内容 ----
class _RoleModel:
    def __init__(self):
        self.roles_called: list[str] = []

    async def ainvoke(self, messages):
        system = messages[0]["content"]
        if "技术面分析师" in system:
            self.roles_called.append("technical_analyst")
            return types.SimpleNamespace(content="趋势向上，支撑1200，量能温和")
        if "看多研究员" in system:
            self.roles_called.append("bull_researcher")
            return types.SimpleNamespace(content="看多论证：突破并站稳1200可看高一线")
        if "看空研究员" in system:
            self.roles_called.append("bear_researcher")
            return types.SimpleNamespace(content="看空论证：上方压力明显，追高风险大")
        if "风控经理" in system:
            self.roles_called.append("risk_manager")
            return types.SimpleNamespace(content="风控评估：单笔止损2%，仓位不超三成")
        if "交易决策者" in system:
            self.roles_called.append("trader")
            return types.SimpleNamespace(content="最终决策：轻仓做多，止损1190")
        return types.SimpleNamespace(content="?")


class _FakeLLM:
    available = True

    def __init__(self, model):
        self.model = model
        self.provider = types.SimpleNamespace(raw_model=model)
        self.breaker = types.SimpleNamespace(on_success=lambda: None, on_failure=lambda: None)

    async def preflight(self):
        pass


def test_research_graph_node_order():
    model = _RoleModel()
    g = build_research_graph(model)
    # 图结构：五个节点 + 首尾
    nodes = set(g.get_graph().nodes.keys())
    assert {"technical_analyst", "bull_researcher", "bear_researcher", "risk_manager", "trader"} <= nodes

    async def _run():
        out = [s async for s in run_research_graph(get_session(), model, symbol=None, question="分析", run_type="diagnose")]
        return out

    import asyncio

    steps = asyncio.run(_run())
    assert [s["node"] for s in steps] == ["technical_analyst", "bull_researcher", "bear_researcher", "risk_manager", "trader"]
    assert "最终决策" in steps[-1]["content"]
    assert model.roles_called == [n for n in NODE_FIELD if n != "trader"] + ["trader"]


def test_deep_chat_records_agent_steps(client: TestClient):
    uname = _uname()
    try:
        user = _register(client, uname)
        token = user["token"]
        h = _auth(token)
        conv = client.post("/api/v1/conversations", json={}, headers=h).json()["data"]

        model = _RoleModel()
        events = []

        async def _run():
            async for ev in chat_service.stream_chat(
                user_id=user["user"]["id"],
                conversation_id=conv["id"],
                symbol=None,
                content="帮我诊断当前趋势",
                run_type="diagnose",
                llm_svc=_FakeLLM(model),
                model=model,
            ):
                events.append(ev)

        import asyncio

        asyncio.run(_run())
        # 深度模式：每个节点一个 delta
        deltas = [e for e in events if e["type"] == "delta"]
        assert len(deltas) == 5
        assert events[-1]["type"] == "done"

        # agent_steps 已记录各节点输出
        db = get_session()
        try:
            run = db.query(AgentRun).filter(AgentRun.conversation_id == conv["id"]).first()
            assert run is not None and run.status == "success"
            steps = db.query(AgentStep).filter(AgentStep.run_id == run.id).all()
            assert [s.step_name for s in steps] == ["technical_analyst", "bull_researcher", "bear_researcher", "risk_manager", "trader"]
            assert "最终决策" in steps[-1].content
            # 清理
            db.query(AgentStep).filter(AgentStep.run_id == run.id).delete()
            db.query(AgentRun).filter(AgentRun.id == run.id).delete()
            db.commit()
        finally:
            db.close()
    finally:
        _cleanup_users(uname)


def test_light_chat_still_react(client: TestClient):
    """run_type=custom 走轻量 ReAct（不产生多节点 agent_steps）。"""
    from tests.test_chat import FakeChatModel, FakeLLMService, _run_stream_chat  # noqa: F401 复用

    uname = _uname()
    try:
        user = _register(client, uname)
        fake = FakeLLMService(FakeChatModel(final_text="普通对话回复"), available=True)
        events = _run_stream_chat(fake, user_id=user["user"]["id"], conversation_id=None, symbol=None, content="hi", run_type="custom")
        assert any(e["type"] == "delta" for e in events)
        assert events[-1]["type"] == "done"
    finally:
        _cleanup_users(uname)

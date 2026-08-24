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
    # 阶段七 7.1：每个节点先 running 再 done（含 summary/duration_ms）
    running = [s for s in steps if s.get("status") == "running"]
    done = [s for s in steps if s.get("status") == "done"]
    assert [s["node"] for s in running] == ["technical_analyst", "bull_researcher", "bear_researcher", "risk_manager", "trader"]
    assert [s["node"] for s in done] == ["technical_analyst", "bull_researcher", "bear_researcher", "risk_manager", "trader"]
    assert "最终决策" in done[-1]["content"]
    assert all(s.get("summary") for s in done)
    assert all(isinstance(s.get("duration_ms"), int) for s in done)
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
        # 阶段七 7.1：每个节点有 running + done 两个 agent_step 事件
        agent_steps_ev = [e for e in events if e["type"] == "agent_step"]
        assert len([e for e in agent_steps_ev if e["status"] == "running"]) == 5
        assert len([e for e in agent_steps_ev if e["status"] == "done"]) == 5

        # agent_steps 已记录各节点输出（含 summary/duration_ms/status）
        db = get_session()
        try:
            run = db.query(AgentRun).filter(AgentRun.conversation_id == conv["id"]).first()
            assert run is not None and run.status == "success"
            assert run.duration_ms is not None and run.duration_ms >= 0
            steps = db.query(AgentStep).filter(AgentStep.run_id == run.id).all()
            assert [s.step_name for s in steps] == ["technical_analyst", "bull_researcher", "bear_researcher", "risk_manager", "trader"]
            assert "最终决策" in steps[-1].content
            assert all(s.status == "done" for s in steps)
            assert all(s.summary for s in steps)
            assert all(s.duration_ms is not None for s in steps)
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


# ---- 7.2：节点失败降级 ----
class _FailRoleModel(_RoleModel):
    """technical_analyst 节点抛异常，其余节点正常。"""

    async def ainvoke(self, messages):
        if "技术面分析师" in messages[0]["content"]:
            raise RuntimeError("technical analysis boom")
        return await super().ainvoke(messages)


def test_research_graph_node_failure_degrades():
    """单节点抛异常 → 图仍完成，失败节点 status=failed + 默认中性观点 + error。"""
    model = _FailRoleModel()

    async def _run():
        return [s async for s in run_research_graph(get_session(), model, symbol=None, question="分析", run_type="diagnose")]

    import asyncio

    steps = asyncio.run(_run())
    finished = [s for s in steps if s.get("status") in ("done", "failed")]
    assert [s["node"] for s in finished] == ["technical_analyst", "bull_researcher", "bear_researcher", "risk_manager", "trader"]
    tech = next(s for s in finished if s["node"] == "technical_analyst")
    assert tech["status"] == "failed"
    assert "默认中性" in tech["content"]
    assert tech.get("error")
    # 其余节点仍正常完成
    assert all(s["status"] == "done" for s in finished if s["node"] != "technical_analyst")


def test_deep_chat_marks_partial_on_node_failure(client: TestClient):
    """深度模式某节点失败 → 结论标注部分节点异常，run 仍 success + error 标记。"""
    uname = _uname()
    try:
        user = _register(client, uname)
        token = user["token"]
        h = _auth(token)
        conv = client.post("/api/v1/conversations", json={}, headers=h).json()["data"]

        model = _FailRoleModel()
        events = []

        async def _run():
            async for ev in chat_service.stream_chat(
                user_id=user["user"]["id"],
                conversation_id=conv["id"],
                symbol=None,
                content="帮我诊断",
                run_type="diagnose",
                llm_svc=_FakeLLM(model),
                model=model,
            ):
                events.append(ev)

        import asyncio

        asyncio.run(_run())
        assert events[-1]["type"] == "done"
        assert events[-1].get("partial") is True

        db = get_session()
        try:
            run = db.query(AgentRun).filter(AgentRun.conversation_id == conv["id"]).first()
            assert run.status == "success"
            assert "部分节点异常" in (run.error or "")
            steps = db.query(AgentStep).filter(AgentStep.run_id == run.id).all()
            failed = [s for s in steps if s.status == "failed"]
            assert [s.step_name for s in failed] == ["technical_analyst"]
            assert "默认中性" in failed[0].content
            # 清理
            db.query(AgentStep).filter(AgentStep.run_id == run.id).delete()
            db.query(AgentRun).filter(AgentRun.id == run.id).delete()
            db.commit()
        finally:
            db.close()
    finally:
        _cleanup_users(uname)

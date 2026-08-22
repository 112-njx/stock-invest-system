"""流式对话服务：保存消息 → 组装上下文/工具 → ReAct Agent → SSE 事件 → 记录 agent_runs/agent_steps。

事件协议（SSE data: json）：
- {"type":"start"}
- {"type":"delta","content":...}     文本增量（分片模拟流式）
- {"type":"tool_call","tool":...,"input":...}
- {"type":"tool_result","tool":...,"preview":...}
- {"type":"done","message_id":...,"conversation_id":...}
- {"type":"error","content":...}     LLM 失败降级文案
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from app.agent.context import build_llm_messages, build_tools, log_context
from app.agent.memory import memory_service
from app.agent.prompts import build_system_prompt as default_system_prompt
from app.agent.research_graph import run_research_graph
from app.agent.sse import cache_delta, cache_done, clear_delta_cache
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.models.agent import UserAgent
from app.repositories import agent_repo, conversation_repo
from app.services import conversation_service, indicator_service, market_service
from app.services.llm import LLMService, get_llm_service
from app.services.llm.llm_service import classify_llm_error
from app.utils.db import SessionLocal

logger = logging.getLogger(__name__)
settings = get_settings()

MAX_HISTORY = 20  # 注入 LLM 的历史消息条数（=最近 10 轮对话，短期记忆，不向量化）
# 深度模式：L 区功能卡片（诊断/交易计划/机会雷达）走多智能体研究图（3.8），其余走单 Agent 工具流
DEEP_RUN_TYPES = {"diagnose", "plan", "radar"}
_AGENT_ROLE = {
    "technical_analyst": "analyst",
    "bull_researcher": "researcher",
    "bear_researcher": "researcher",
    "risk_manager": "manager",
    "trader": "trader",
}


def _fallback_text() -> str:
    return "当前 AI 服务暂不可用（未配置 API Key 或服务异常），请稍后重试。以下为数据可用的说明：无法生成智能分析，请核对行情与风险后自行决策。"


def _rule_based_analysis(db, symbol_id: int | None) -> str:
    """熔断降级（5.4）：基于规则的技术指标状态描述（MACD/KDJ），不依赖 LLM。"""
    if not symbol_id:
        return "未绑定分析标的，无法生成基础技术分析。"
    try:
        rows = indicator_service.compute_indicators(db, str(symbol_id), "1d", ["macd", "kdj"], limit=30)
    except Exception as e:  # noqa: BLE001
        logger.warning("rule-based analysis failed: %s", e)
        return "行情数据暂时不可用，无法生成基础技术分析。"
    if not rows:
        return "暂无该标的的行情数据，无法生成基础技术分析。"
    last = rows[-1]
    dif, dea = last.get("macd_dif"), last.get("macd_dea")
    k, d = last.get("kdj_k"), last.get("kdj_d")
    signals: list[str] = []
    trend: str | None = None
    if dif is not None and dea is not None:
        signals.append("MACD金叉" if dif > dea else "MACD死叉")
        trend = "偏多" if dif > dea else "偏空"
    if k is not None and d is not None:
        if k > 80:
            signals.append("KDJ超买")
        elif k < 20:
            signals.append("KDJ超卖")
        elif k > d:
            signals.append("KDJ多头排列")
        else:
            signals.append("KDJ空头排列")
        if trend is None:
            trend = "偏多" if k > d else "偏空"
    if not signals:
        return "暂无有效指标数据，无法生成基础技术分析。"
    return "、".join(signals) + (f"，短期趋势{trend}" if trend else "")


def _degraded_text(db, symbol_id: int | None, error_code: str) -> str:
    """按错误码分级生成降级文案（5.4）。"""
    if error_code in ("TOKEN_INVALID", "TOKEN_QUOTA"):
        return "您的DeepSeek API Key无效或余额不足，请检查配置"
    if error_code == "PROVIDER_UNAVAILABLE":
        return "AI服务暂时不可用，已切换基础分析模式。\n" + _rule_based_analysis(db, symbol_id)
    if error_code == "CONTENT_FILTERED":
        return "内容违规，已被过滤，请调整提问后重试。"
    return _fallback_text()


def _load_agent(db: Session, user_id: int, agent_id: int | None) -> UserAgent | None:
    if agent_id is None:
        return None
    return agent_repo.get_agent(db, user_id, agent_id)


async def _run_react(
    db: Session,
    run,
    user_msg,
    conv,
    symbol_id,
    messages: list[dict],
    tools,
    agent_model,
    llm_svc,
) -> AsyncIterator[dict]:
    """轻量模式：ReAct Agent（工具按需取数）。"""
    from langchain.agents import create_agent

    compiled = create_agent(agent_model, tools)  # system_prompt 已在 messages 首位
    parts: list[str] = []
    step_idx = 0
    try:
        async for update in compiled.astream({"messages": messages}, stream_mode="updates"):
            for ev in _emit_update(db, run, update, parts, step_idx):
                yield ev
            step_idx += 1
        full_text = "".join(parts).strip() or _fallback_text()
        llm_svc.breaker.on_success()
        assistant_msg = _save_result(db, run, user_msg, conv, symbol_id, full_text, 0, "success")
        saved_facts = await _extract_and_save_memory(db, run.user_id, conv.id, user_msg.content, full_text, llm_svc)
        for f in saved_facts:
            yield {"type": "memory_saved", "summary": f["content"], "importance": int(f.get("importance", 5))}
        yield {"type": "done", "message_id": assistant_msg.id, "conversation_id": conv.id, "run_id": run.id}
    except Exception as e:  # noqa: BLE001
        logger.exception("agent run failed: %s", e)
        llm_svc.breaker.on_failure()
        yield _yield_failure(db, run, user_msg, conv, symbol_id, e)


async def _run_deep(
    db: Session,
    run,
    user_msg,
    conv,
    symbol_id,
    symbol: str | None,
    content: str,
    run_type: str,
    agent_model,
    llm_svc,
) -> AsyncIterator[dict]:
    """深度模式：LangGraph 多智能体研究图（技术分析→多空辩论→风控→决策）。"""
    parts: list[str] = []
    try:
        async for step in run_research_graph(db, agent_model, symbol=symbol, question=content, run_type=run_type):
            node, text = step["node"], step["content"]
            parts.append(text)
            agent_repo.add_step(db, run.id, node, _AGENT_ROLE.get(node, "analyst"), text, {"idx": len(parts)})
            yield {"type": "delta", "content": text, "node": node}
        db.commit()
        full_text = "\n\n".join(parts).strip() or _fallback_text()
        llm_svc.breaker.on_success()
        assistant_msg = _save_result(db, run, user_msg, conv, symbol_id, full_text, 0, "success")
        saved_facts = await _extract_and_save_memory(db, run.user_id, conv.id, content, full_text, llm_svc)
        for f in saved_facts:
            yield {"type": "memory_saved", "summary": f["content"], "importance": int(f.get("importance", 5))}
        yield {"type": "done", "message_id": assistant_msg.id, "conversation_id": conv.id, "run_id": run.id}
    except Exception as e:  # noqa: BLE001
        logger.exception("research graph run failed: %s", e)
        llm_svc.breaker.on_failure()
        yield _yield_failure(db, run, user_msg, conv, symbol_id, e)


def _yield_failure(db, run, user_msg, conv, symbol_id, exc: Exception) -> dict:
    """运行失败：按错误码分级降级文案入库 + 返回标准化 error 事件（阶段五 5.3/5.4）。"""
    error_ev = classify_llm_error(exc)
    text = _degraded_text(db, symbol_id, error_ev["code"])
    assistant_msg = _save_result(db, run, user_msg, conv, symbol_id, text, 0, "failed", error_ev["message"])
    return {**error_ev, "message_id": assistant_msg.id, "conversation_id": conv.id, "run_id": run.id}


async def stream_chat(
    *,
    user_id: int,
    conversation_id: int | None,
    symbol: str | None,
    content: str,
    agent_id: int | None = None,
    run_type: str = "custom",
    llm_svc: LLMService | None = None,
    model: Any | None = None,
) -> AsyncIterator[dict]:
    """流式对话主流程（yield SSE 事件）。llm_svc/model 供测试注入。"""
    llm_svc = llm_svc or get_llm_service()
    db: Session = SessionLocal()
    try:
        # ---- 会话与用户消息 ----
        conv = None
        if conversation_id is not None:
            conv = conversation_repo.get_conversation(db, user_id, conversation_id)
            if conv is None:
                raise ApiError(status_code=404, code=40410, msg="会话不存在")
        if conv is None:
            conv = conversation_service.create_conversation(db, user_id, None)

        symbol_id = market_service.resolve_symbol_id(db, symbol) if symbol else None
        if symbol and symbol_id is None:
            raise ApiError(status_code=400, code=40002, msg=f"标的不存在: {symbol}")

        user_msg = conversation_repo.add_message(db, conv.id, "user", content, symbol_id=symbol_id)
        db.commit()
        clear_delta_cache(conv.id)  # 新消息开始：清空旧 delta 断点续传缓存
        yield {"type": "start"}

        # ---- 上下文组装 ----
        agent = _load_agent(db, user_id, agent_id)
        if agent:
            system_prompt = agent.system_prompt or default_system_prompt(assistant_name=agent.name)
        else:
            system_prompt = default_system_prompt()
        tools = build_tools(db, include_memory=[memory_service.memory_tool(db, user_id)])
        history = [
            {"role": m.role, "content": m.content}
            for m in conversation_repo.list_messages(db, conv.id)
            if m.id != user_msg.id
        ][-MAX_HISTORY:]
        memory_context = memory_service.retrieve_memory(db, user_id, content)
        messages = build_llm_messages(
            system_prompt=system_prompt, history=history, user_content=content, memory_context=memory_context or None
        )
        log_context(system_prompt, messages, tools)

        # ---- 运行记录 ----
        run = agent_repo.create_run(
            db, user_id, run_type, content, agent_id=agent_id, conversation_id=conv.id, symbol_id=symbol_id
        )
        db.commit()

        # ---- LLM 不可用降级 ----
        # 仅按服务可用性判定；model 为可选注入（None 时下面用 llm_svc.provider.raw_model 兜底），不得作为降级条件
        if not llm_svc.available:
            text = _degraded_text(db, symbol_id, "PROVIDER_UNAVAILABLE")
            assistant_msg = _save_result(db, run, user_msg, conv, symbol_id, text, 0, "failed", "AI 服务不可用")
            yield {"type": "delta", "content": text}
            yield {"type": "done", "message_id": assistant_msg.id, "conversation_id": conv.id, "run_id": run.id}
            return

        # ---- 运行 Agent（深度模式走研究图，其余走 ReAct 工具流）----
        try:
            await llm_svc.preflight()
        except Exception as e:  # noqa: BLE001
            logger.warning("llm preflight failed: %s", e)
            yield _yield_failure(db, run, user_msg, conv, symbol_id, e)
            return
        agent_model = model if model is not None else llm_svc.provider.raw_model
        if run_type in DEEP_RUN_TYPES:
            gen = _run_deep(db, run, user_msg, conv, symbol_id, symbol, content, run_type, agent_model, llm_svc)
        else:
            gen = _run_react(db, run, user_msg, conv, symbol_id, messages, tools, agent_model, llm_svc)
        async for ev in _stream_with_timeouts(gen, db, run, user_msg, conv, symbol_id):
            yield ev
    finally:
        db.close()


def _emit_update(db: Session, run, update: dict, parts: list[str], idx: int) -> list[dict]:
    """把一次 LangGraph 节点更新转为 SSE 事件（同步调用，返回事件列表）。"""
    events: list[dict] = []
    for _node, state in update.items():
        msgs = state.get("messages", [])
        for m in msgs:
            if getattr(m, "type", "") == "ai":
                tool_calls = getattr(m, "tool_calls", None) or []
                if tool_calls:
                    for tc in tool_calls:
                        args = tc.get("args") or tc.get("input") or {}
                        events.append({"type": "tool_call", "tool": tc.get("name", "?"), "input": args})
                        agent_repo.add_step(
                            db, run.id, f"tool:{tc.get('name', '?')}", "assistant", json.dumps(args, ensure_ascii=False), {"idx": idx}
                        )
                if m.content:
                    parts.append(m.content)
                    text = m.content
                    events.append({"type": "delta", "content": text})
                    agent_repo.add_step(db, run.id, f"agent:step{idx}", "assistant", text, {"idx": idx})
            elif getattr(m, "type", "") == "tool":
                tool_name = getattr(m, "name", "?")
                preview = str(getattr(m, "content", ""))[:500]
                events.append({"type": "tool_result", "tool": tool_name, "preview": preview})
                agent_repo.add_step(db, run.id, f"tool_result:{tool_name}", "tool", preview, {"idx": idx})
    if events:
        db.commit()
    return events


async def _extract_and_save_memory(db: Session, user_id: int, source_id: int | None, user_msg: str, assistant_msg: str, llm_svc) -> list[dict]:
    """对话结束后抽取关键事实入库（best-effort，失败不影响主链路）。返回已抽取事实列表（供 memory_saved 事件）。"""
    try:
        facts = await memory_service.aextract_facts(user_msg, assistant_msg, llm_svc)
        if facts:
            memory_service.save_memory(db, user_id, "rule", source_id, facts)
            return facts
    except Exception as e:  # noqa: BLE001
        logger.warning("memory extract/save failed: %s", e)
    return []


def _save_result(db, run, user_msg, conv, symbol_id, text, tokens, status, error=None):
    """保存 assistant 消息 + 更新 run 状态（同事务），返回 assistant 消息。"""
    assistant_msg = conversation_repo.add_message(db, conv.id, "assistant", text, symbol_id=symbol_id, tokens=tokens)
    agent_repo.finish_run(db, run, status=status, output=text, tokens=tokens, error=error)
    db.commit()
    db.refresh(assistant_msg)
    return assistant_msg


async def _stream_with_timeouts(gen, db, run, user_msg, conv, symbol_id) -> AsyncIterator[dict]:
    """给 Agent 事件流加三级超时 + delta 序号/断点续传缓存（阶段五 5.1/5.2）。

    - 首字超时：首个输出（delta/tool_call）前等待上限 SSE_FIRST_TOKEN_TIMEOUT；
    - 单 delta 间隔超时：相邻输出间隔上限 SSE_INTER_DELTA_TIMEOUT；
    - 总流式超时：SSE_TOTAL_TIMEOUT。
    每个 delta 事件携带递增 seq 并缓存到 Redis；done 事件缓存供断点续传。
    超时后保存已生成内容 + 返回 ``{"type":"done","truncated":true,"reason":"timeout"}``。
    """
    start = time.monotonic()
    first = True
    seq = 0
    partial_parts: list[str] = []
    try:
        while True:
            remaining = settings.SSE_TOTAL_TIMEOUT - (time.monotonic() - start)
            if remaining <= 0:
                raise TimeoutError("total streaming timeout")
            step_timeout = settings.SSE_FIRST_TOKEN_TIMEOUT if first else settings.SSE_INTER_DELTA_TIMEOUT
            try:
                ev = await asyncio.wait_for(gen.__anext__(), timeout=min(step_timeout, remaining))
            except TimeoutError:
                logger.warning("sse stream timeout user=%s conv=%s", run.user_id, conv.id)
                full_text = "".join(partial_parts).strip() or _fallback_text()
                assistant_msg = _save_result(db, run, user_msg, conv, symbol_id, full_text, 0, "failed", "timeout")
                done_ev = {
                    "type": "done",
                    "message_id": assistant_msg.id,
                    "conversation_id": conv.id,
                    "run_id": run.id,
                    "truncated": True,
                    "reason": "timeout",
                }
                cache_done(conv.id, done_ev)
                yield done_ev
                return
            if ev.get("type") == "delta":
                partial_parts.append(ev.get("content", ""))
                seq += 1
                ev = {**ev, "seq": seq}
                cache_delta(conv.id, ev)
            elif ev.get("type") == "done":
                cache_done(conv.id, ev)
            first = False
            yield ev
    except StopAsyncIteration:
        return

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
from app.agent.strategy_gen import generate_strategy
from app.agent.token_budget import estimate_messages_tokens, estimate_tokens, fit_window_to_budget
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.models.agent import UserAgent
from app.repositories import agent_repo, conversation_repo
from app.services import conversation_service, indicator_service, market_service, strategy_service
from app.services.llm import LLMError, LLMService, get_llm_service
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

# 阶段八 8.1：长会话滑动窗口摘要
_SUMMARY_PROMPT = """请将以下对话历史压缩为不超过200字的摘要，保留关键信息（用户交易偏好/规则、已讨论的标的、重要结论与待办）。只输出摘要正文，不要任何前缀或说明。

对话：
{conversation}
"""


def _assemble_history(all_msgs: list[dict], summary: str | None, max_history: int = MAX_HISTORY) -> list[dict]:
    """组装消息历史：最近 max_history 条完整 + 可选会话摘要替代早期对话（阶段八 8.1）。"""
    history = all_msgs[-max_history:]
    if summary:
        history = [{"role": "system", "content": f"之前对话摘要：{summary}"}] + history
    return history


def _estimate_tools_tokens(tools: list) -> int:
    """粗略估算工具描述 token（阶段八 8.2：工具名 + description）。"""
    total = 0
    for t in tools:
        name = getattr(t, "name", "") or t.__class__.__name__
        desc = getattr(t, "description", "") or ""
        total += estimate_tokens(str(name)) + estimate_tokens(str(desc))
    return total


def _usage_event(prompt_tokens: int, completion_text: str) -> dict:
    """构造 usage 事件（阶段八 8.2：前端可展示 token 用量）。"""
    completion = estimate_tokens(completion_text)
    return {"type": "usage", "prompt": prompt_tokens, "completion": completion, "total": prompt_tokens + completion}


async def _generate_conversation_summary(conv_id: int, llm_svc) -> None:
    """异步生成/更新会话摘要（best-effort：失败不影响主链路，独立 DB 会话）。"""
    try:
        if not getattr(llm_svc, "available", False):
            return
        db: Session = SessionLocal()
        try:
            msgs = conversation_repo.list_messages(db, conv_id)
            # 只摘要早期轮次（去掉最近 MAX_HISTORY 条 = 最近 10 轮）
            early = msgs[:-MAX_HISTORY] if len(msgs) > MAX_HISTORY else msgs
            if not early:
                return
            conversation = "\n".join(f"{m.role}: {m.content}" for m in early)
            result = await llm_svc.ainvoke(
                [{"role": "user", "content": _SUMMARY_PROMPT.format(conversation=conversation[:8000])}]
            )
            summary = (result.text or "").strip()[:200]
            if summary:
                conversation_repo.update_summary(db, conv_id, summary)
                db.commit()
        finally:
            db.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("conversation summary failed conv=%s: %s", conv_id, e)


def _schedule_summary_update(conv_id: int, llm_svc) -> None:
    """每满 10 轮异步更新会话摘要（不阻塞当前响应）。"""
    try:
        asyncio.create_task(_generate_conversation_summary(conv_id, llm_svc))
    except RuntimeError:  # 无运行中事件循环时忽略
        pass


# 阶段八 8.7：会话标题自动生成
_TITLE_PROMPT = """请为以下对话生成一个简短标题（不超过15个字），概括对话主题。只输出标题正文，不要任何前缀、标点或说明。

对话首条消息：
{content}
"""


async def _generate_conversation_title(conv_id: int, first_msg: str, llm_svc, queue: "asyncio.Queue | None" = None) -> str | None:
    """异步生成会话标题（best-effort：失败不影响对话）。可选 queue 推送 title 事件。

    始终在 finally 向队列放入结果/哨兵，避免调用方空等超时。
    """
    title: str | None = None
    try:
        if not getattr(llm_svc, "available", False):
            title = None
        else:
            result = await llm_svc.ainvoke(
                [{"role": "user", "content": _TITLE_PROMPT.format(content=first_msg[:500])}]
            )
            title = (result.text or "").strip()[:15] or None
        if title:
            db: Session = SessionLocal()
            try:
                conversation_repo.update_title(db, conv_id, title)
                db.commit()
            finally:
                db.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("conversation title failed conv=%s: %s", conv_id, e)
        title = None
    finally:
        if queue is not None:
            try:
                evt = {"type": "title", "title": title, "conversation_id": conv_id} if title else None
                await queue.put(("title", evt))
            except Exception:  # noqa: BLE001
                pass
    return title


def _schedule_title_update(conv_id: int, first_msg: str, llm_svc, queue: "asyncio.Queue | None" = None) -> None:
    """会话首条消息后异步生成标题（不阻塞当前响应）。"""
    try:
        asyncio.create_task(_generate_conversation_title(conv_id, first_msg, llm_svc, queue))
    except RuntimeError:
        pass


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
    prompt_tokens: int = 0,
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
        yield _usage_event(prompt_tokens, full_text)
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
    prompt_tokens: int = 0,
) -> AsyncIterator[dict]:
    """深度模式：LangGraph 多智能体研究图（技术分析→多空辩论→风控→决策）。"""
    parts: list[str] = []
    failed_nodes: list[str] = []
    started = time.monotonic()
    try:
        async for step in run_research_graph(db, agent_model, symbol=symbol, question=content, run_type=run_type):
            node = step["node"]
            status = step.get("status", "done")
            if status == "running":
                yield {"type": "agent_step", "node": node, "status": "running"}
                continue
            text = step.get("content", "")
            summary = step.get("summary", "")
            duration_ms = step.get("duration_ms", 0)
            error = step.get("error")
            if status == "failed":
                failed_nodes.append(node)
            parts.append(text)
            meta = {"idx": len(parts)}
            if error:
                meta["error"] = error
            agent_repo.add_step(
                db,
                run.id,
                node,
                _AGENT_ROLE.get(node, "analyst"),
                text,
                meta,
                summary=summary,
                duration_ms=duration_ms,
                status=status,
            )
            yield {"type": "delta", "content": text, "node": node}
            step_ev = {"type": "agent_step", "node": node, "status": status, "summary": summary, "duration_ms": duration_ms}
            if error:
                step_ev["error"] = error
            yield step_ev
        db.commit()
        total_duration_ms = int((time.monotonic() - started) * 1000)
        full_text = "\n\n".join(parts).strip() or _fallback_text()
        # 阶段七 7.2：部分节点异常时在结论标注 + agent_runs 标记，run 仍为 success（图已完成）
        partial = bool(failed_nodes)
        if partial:
            full_text += "\n\n（部分节点异常，结论仅供参考）"
        llm_svc.breaker.on_success()
        assistant_msg = _save_result(
            db, run, user_msg, conv, symbol_id, full_text, 0, "success",
            duration_ms=total_duration_ms,
            error=f"部分节点异常: {','.join(failed_nodes)}" if partial else None,
        )
        saved_facts = await _extract_and_save_memory(db, run.user_id, conv.id, content, full_text, llm_svc)
        for f in saved_facts:
            yield {"type": "memory_saved", "summary": f["content"], "importance": int(f.get("importance", 5))}
        yield _usage_event(prompt_tokens, full_text)
        done_ev = {"type": "done", "message_id": assistant_msg.id, "conversation_id": conv.id, "run_id": run.id}
        if partial:
            done_ev["partial"] = True
        yield done_ev
    except Exception as e:  # noqa: BLE001
        logger.exception("research graph run failed: %s", e)
        llm_svc.breaker.on_failure()
        yield _yield_failure(db, run, user_msg, conv, symbol_id, e)


async def _run_strategy(db, run, user_msg, conv, symbol_id, content, llm_svc) -> AsyncIterator[dict]:
    """策略生成分支（阶段八 8.6）：生成→三级校验→重试→保存→push strategy_ready。

    单次长调用（非流式），不走 _stream_with_timeouts 的流式超时（keepalive 由 API 层保证）。
    """
    try:
        out = await generate_strategy(content, llm_svc=llm_svc)
        params = out.params.model_dump() if hasattr(out.params, "model_dump") else dict(out.params)
        title = (out.strategy_name or "").strip()[:128] or "未命名策略"
        strategy = strategy_service.create_strategy(
            db, run.user_id, title, out.description, out.code, params, "draft"
        )
        text = (
            f"已为你生成策略「{out.strategy_name}」：\n\n"
            f"{out.description}\n\n"
            f"```python\n{out.code}\n```\n\n"
            f"风险提示：{out.risk_warning or '无'}"
        )
        assistant_msg = _save_result(db, run, user_msg, conv, symbol_id, text, 0, "success")
        yield {"type": "delta", "content": text}
        yield {"type": "strategy_ready", "strategy_id": strategy.id, "auto_backtest": True}
        yield {"type": "done", "message_id": assistant_msg.id, "conversation_id": conv.id, "run_id": run.id}
    except LLMError as e:
        # 生成失败（含重试耗尽）：返回友好提示（含模板库入口）
        text = str(e) or "策略生成遇到问题，请尝试调整描述或基于模板创建。"
        assistant_msg = _save_result(db, run, user_msg, conv, symbol_id, text, 0, "failed", str(e))
        yield {"type": "delta", "content": text}
        yield {"type": "done", "message_id": assistant_msg.id, "conversation_id": conv.id, "run_id": run.id}
    except Exception as e:  # noqa: BLE001
        logger.exception("strategy generation failed: %s", e)
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

        # 阶段八 8.7：会话首条用户消息 → 异步生成标题（不阻塞，done 后经队列推送 title 事件）
        title_queue: asyncio.Queue = asyncio.Queue()
        is_first_msg = conversation_repo.count_messages(db, conv.id) == 1
        if is_first_msg and llm_svc.available:
            _schedule_title_update(conv.id, content, llm_svc, title_queue)

        # ---- 上下文组装 ----
        agent = _load_agent(db, user_id, agent_id)
        if agent:
            system_prompt = agent.system_prompt or default_system_prompt(assistant_name=agent.name)
        else:
            system_prompt = default_system_prompt()
        tools = build_tools(db, include_memory=[memory_service.memory_tool(db, user_id)])
        _all_msgs = [
            {"role": m.role, "content": m.content}
            for m in conversation_repo.list_messages(db, conv.id)
            if m.id != user_msg.id
        ]
        memory_context = memory_service.retrieve_memory(db, user_id, content)
        # 阶段八 8.2：按 token 预算裁剪完整轮数；8.1：早期对话用摘要替代
        tools_tokens = _estimate_tools_tokens(tools)
        window = fit_window_to_budget(
            system_prompt=system_prompt,
            all_history=_all_msgs,
            summary=conv.summary,
            user_content=content,
            memory_context=memory_context or None,
            tools_tokens=tools_tokens,
        )
        history = _assemble_history(_all_msgs, conv.summary, window)
        messages = build_llm_messages(
            system_prompt=system_prompt, history=history, user_content=content, memory_context=memory_context or None
        )
        prompt_tokens = estimate_messages_tokens(messages) + tools_tokens
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
        if run_type == "strategy":
            # 阶段八 8.6：策略生成（单次长调用，绕过流式超时，keepalive 由 API 层保证）
            async for ev in _run_strategy(db, run, user_msg, conv, symbol_id, content, llm_svc):
                yield ev
        else:
            if run_type in DEEP_RUN_TYPES:
                gen = _run_deep(db, run, user_msg, conv, symbol_id, symbol, content, run_type, agent_model, llm_svc, prompt_tokens)
            else:
                gen = _run_react(db, run, user_msg, conv, symbol_id, messages, tools, agent_model, llm_svc, prompt_tokens)
            async for ev in _stream_with_timeouts(gen, db, run, user_msg, conv, symbol_id):
                yield ev
        # 阶段八 8.7：done 后短等待推送 title 事件（best-effort）
        if is_first_msg and llm_svc.available:
            try:
                _kind, title_ev = await asyncio.wait_for(title_queue.get(), timeout=settings.TITLE_WAIT_TIMEOUT)
                if title_ev:
                    yield title_ev
            except (TimeoutError, asyncio.CancelledError):
                pass
        # 阶段八 8.1：每满 10 轮异步更新会话摘要（不阻塞当前响应）
        msg_count = conversation_repo.count_messages(db, conv.id)
        if msg_count >= MAX_HISTORY and msg_count % MAX_HISTORY == 0:
            _schedule_summary_update(conv.id, llm_svc)
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


def _save_result(db, run, user_msg, conv, symbol_id, text, tokens, status, error=None, duration_ms=None):
    """保存 assistant 消息 + 更新 run 状态（同事务），返回 assistant 消息。"""
    assistant_msg = conversation_repo.add_message(db, conv.id, "assistant", text, symbol_id=symbol_id, tokens=tokens)
    agent_repo.finish_run(db, run, status=status, output=text, tokens=tokens, duration_ms=duration_ms, error=error)
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
            # 仅内容事件翻转「首字」标记：agent_step(running/done) 等非文本事件不消耗首字超时预算
            if ev.get("type") in ("delta", "tool_call"):
                first = False
            yield ev
    except StopAsyncIteration:
        return

"""多智能体编排（3.8 + 阶段七）：LangGraph StateGraph — 技术分析 → 多空研究员辩论 → 风控 → 交易决策。

借鉴 TradingAgents-CN trading_graph 组织架构（分析师团队→研究员团队辩论→风控→交易员），
深度模式（诊断/交易计划/机会雷达）走此图，agent_steps 记录各节点输出。

阶段七 7.1：改用 astream_events 逐节点推送 running/done 事件（含 summary/duration_ms），供 agent_step SSE + 落库。
"""

import logging
import time
from collections.abc import AsyncIterator
from operator import add
from typing import Annotated, Any, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.services import indicator_service, market_service

logger = logging.getLogger(__name__)

# 节点 → 状态字段（astream updates 中取值用）
NODE_FIELD = {
    "technical_analyst": "analysis",
    "bull_researcher": "bull_arg",
    "bear_researcher": "bear_arg",
    "risk_manager": "risk_assessment",
    "trader": "final_decision",
}

# 各节点失败时的默认中性观点（阶段七 7.2：单节点失败不中断图）
_NEUTRAL_TEXT = {
    "technical_analyst": "技术分析暂不可用，默认中性。",
    "bull_researcher": "看多分析暂不可用，默认中性。",
    "bear_researcher": "看空分析暂不可用，默认中性。",
    "risk_manager": "风控评估暂不可用，默认中性。",
    "trader": "交易决策暂不可用，默认中性（暂不建议操作）。",
}


def _summarize(text: str, limit: int = 200) -> str:
    """把节点输出压成简短摘要（去多余空白 + 截断，供 summary 字段与 SSE 展示）。"""
    t = " ".join(str(text).split()).strip()
    return t[:limit] + ("…" if len(t) > limit else "")


def _merge_errors(a: dict, b: dict) -> dict:
    """节点错误映射的合并 reducer（阶段七 7.2：失败节点名→错误信息）。"""
    merged = dict(a or {})
    merged.update(b or {})
    return merged


class ResearchState(TypedDict, total=False):
    symbol: str
    question: str
    run_type: str
    market_context: str
    analysis: str
    bull_arg: str
    bear_arg: str
    risk_assessment: str
    final_decision: str
    # 阶段七 7.2：失败节点累计（Annotated + add reducer 追加，避免覆盖）
    failed_nodes: Annotated[list[str], add]
    node_errors: Annotated[dict[str, str], _merge_errors]


def _prompt(node: str, state: ResearchState) -> str:
    base = (
        f"标的信息：{state.get('symbol', '')}\n"
        f"行情/指标数据：\n{state.get('market_context', '（无数据）')}\n"
        f"问题：{state.get('question', '')}"
    )
    prev = state
    if node == "technical_analyst":
        return (
            "你是技术面分析师。基于以下行情数据，给出结构化分析：趋势、量价、关键支撑/压力、动量。"
            "数据不可用必须明说，禁止编造。\n" + base
        )
    if node == "bull_researcher":
        return (
            "你是看多研究员。基于技术分析结论，给出支持上涨/偏多的论证（触发条件、目标位、确认信号）。"
            "数据不可用必须明说。\n" + base + f"\n技术分析：\n{prev.get('analysis', '')}"
        )
    if node == "bear_researcher":
        return (
            "你是看空研究员。基于技术分析结论，给出看空/偏空论证（风险点、失效位、下行目标）。"
            "数据不可用必须明说。\n" + base + f"\n技术分析：\n{prev.get('analysis', '')}"
        )
    if node == "risk_manager":
        return (
            "你是风控经理。评估多空论证的风险：仓位上限、止损位、最大回撤，区分事实/假设/不确定。"
            "数据不可用必须明说。\n"
            + base
            + f"\n看多论证：\n{prev.get('bull_arg', '')}\n看空论证：\n{prev.get('bear_arg', '')}"
        )
    # trader（交易决策）
    run_type = state.get("run_type", "diagnose")
    if run_type == "plan":
        out = "请输出一份可执行交易计划：方向判断、关键价位、入场触发、止损、止盈、仓位、等待条件。结论优先。"
    elif run_type == "radar":
        out = "请输出未来24小时机会雷达：触发条件、确认信号、失效位、主要风险，区分事实/假设/不确定。简洁可执行。"
    else:  # diagnose
        out = "请给出偏多/震荡/偏空判断及对应触发条件，并给出具体行动：观察价位、入场确认、失效止损、止盈减仓。结论优先。"
    return (
        "你是交易决策者。综合技术分析、多空辩论与风控评估，给出最终可执行的交易决策。数据不可用必须明说，禁止编造。\n"
        + base
        + f"\n技术分析：\n{prev.get('analysis', '')}\n看多论证：\n{prev.get('bull_arg', '')}\n"
        + f"看空论证：\n{prev.get('bear_arg', '')}\n风控评估：\n{prev.get('risk_assessment', '')}\n输出要求：{out}"
    )


def _build_market_context(db: Session, symbol: str) -> str:
    """预取行情快照 + 最近日K + 指标，拼成上下文文本。"""
    lines: list[str] = []
    symbol_id = market_service.resolve_symbol_id(db, symbol) if symbol else None
    if symbol_id:
        snaps = market_service.get_snapshots(db, [symbol_id])
        if snaps:
            s = snaps[0]
            lines.append(
                f"快照: 最新价={s.get('price')} 涨跌额={s.get('change')} 涨跌幅={s.get('change_pct')}% "
                f"今开={s.get('open')} 最高={s.get('high')} 最低={s.get('low')} 昨收={s.get('pre_close')}"
            )
            if s.get("extra"):
                lines.append(f"特殊字段: {s['extra']}")
    try:
        rows = indicator_service.compute_indicators(db, symbol, "1d", ["macd", "kdj"], limit=30)
        if rows:
            last = rows[-1]
            lines.append(
                f"近30日K线最新: 收盘={last.get('close')} 量={last.get('volume')} "
                f"MACD(DIF/DEA/HIST)={last.get('macd_dif')}/{last.get('macd_dea')}/{last.get('macd_hist')} "
                f"KDJ(K/D/J)={last.get('kdj_k')}/{last.get('kdj_d')}/{last.get('kdj_j')}"
            )
    except ValueError as e:
        lines.append(f"指标计算不可用: {e}")
    return "\n".join(lines) if lines else "（无可用行情数据，请明确说明不可用）"


async def _stream_llm_text(model, prompt: str, node: str) -> str:
    """逐 token 流式产出节点文本：经 stream_writer 推送带 node 的 delta，返回完整文本。"""
    writer = get_stream_writer()
    parts: list[str] = []
    async for chunk in model.astream(
        [{"role": "system", "content": prompt}, {"role": "user", "content": "请给出分析。"}]
    ):
        text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
        if text:
            parts.append(text)
            writer({"type": "delta", "node": node, "content": text})
    return "".join(parts)


def _make_node(model: Any, node: str, field: str):
    async def _node(state: ResearchState) -> dict:
        # 阶段七 7.2：单节点失败不中断图，返回默认中性观点并记录失败节点与错误信息
        try:
            text = await _stream_llm_text(model, _prompt(node, state), node)
        except Exception as e:  # noqa: BLE001
            logger.warning("research node %s failed: %s", node, e)
            return {field: _NEUTRAL_TEXT[node], "failed_nodes": [node], "node_errors": {node: str(e)}}
        return {field: text}

    return _node


def build_research_graph(model: Any):
    g = StateGraph(ResearchState)
    for node, field in NODE_FIELD.items():
        g.add_node(node, _make_node(model, node, field))
    g.add_edge(START, "technical_analyst")
    g.add_edge("technical_analyst", "bull_researcher")
    g.add_edge("bull_researcher", "bear_researcher")
    g.add_edge("bear_researcher", "risk_manager")
    g.add_edge("risk_manager", "trader")
    g.add_edge("trader", END)
    return g.compile()


async def run_research_graph(
    db: Session, model: Any, *, symbol: str | None, question: str, run_type: str = "diagnose"
) -> AsyncIterator[dict]:
    """执行研究图，逐节点 yield SSE 事件（阶段七 7.1/7.2）：

    - ``{"node": ..., "status": "running"}`` 节点开始
    - ``{"node": ..., "status": "done"|"failed", "content": ..., "summary": ..., "duration_ms": ..., "error"?}`` 节点完成

    用 ``astream(stream_mode="updates")`` 保证节点按图顺序确定性产出（避免 astream_events 乱序）。
    """
    context = _build_market_context(db, symbol) if symbol else "（未绑定标的）"
    state: ResearchState = {
        "symbol": symbol or "未指定标的",
        "question": question,
        "run_type": run_type,
        "market_context": context,
    }
    graph = build_research_graph(model)
    nodes = list(NODE_FIELD.keys())
    if not nodes:
        return

    # 第一个节点开始
    started: dict[str, float] = {nodes[0]: time.monotonic()}
    yield {"node": nodes[0], "status": "running"}

    idx = 0
    async for mode, data in graph.astream(state, stream_mode=["updates", "custom"]):
        # custom：节点内 stream_writer 推送的 token 级 delta，逐字透传
        if mode == "custom":
            yield data
            continue
        # updates：节点完成（顺序确定性），继续按原逻辑产出 done/failed 事件
        for node, delta in data.items():
            field = NODE_FIELD.get(node)
            content = delta.get(field) if field else None
            if not content:
                continue
            duration_ms = int((time.monotonic() - started.get(node, time.monotonic())) * 1000)
            is_failed = node in (delta.get("failed_nodes") or [])
            error = (delta.get("node_errors") or {}).get(node) if is_failed else None
            evt: dict = {
                "node": node,
                "status": "failed" if is_failed else "done",
                "content": content,
                "summary": _summarize(content),
                "duration_ms": duration_ms,
            }
            if error:
                evt["error"] = error
            yield evt

            # 下一个节点开始（线性图：上一个完成后紧接开始）
            idx += 1
            if idx < len(nodes):
                nxt = nodes[idx]
                started[nxt] = time.monotonic()
                yield {"node": nxt, "status": "running"}

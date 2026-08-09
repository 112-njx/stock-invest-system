"""多智能体编排（3.8）：LangGraph StateGraph — 技术分析 → 多空研究员辩论 → 风控 → 交易决策。

借鉴 TradingAgents-CN trading_graph 组织架构（分析师团队→研究员团队辩论→风控→交易员），
深度模式（诊断/交易计划/机会雷达）走此图，agent_steps 记录各节点输出。
"""

import logging
from collections.abc import AsyncIterator
from typing import Any, TypedDict

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


async def _llm_text(model, prompt: str) -> str:
    resp = await model.ainvoke([{"role": "system", "content": prompt}, {"role": "user", "content": "请给出分析。"}])
    return resp.content if isinstance(resp.content, str) else str(resp.content)


def _make_node(model: Any, node: str, field: str):
    async def _node(state: ResearchState) -> dict:
        text = await _llm_text(model, _prompt(node, state))
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
    """执行研究图，yield {node, content} 各节点输出（供 agent_steps 记录 + SSE）。"""
    context = _build_market_context(db, symbol) if symbol else "（未绑定标的）"
    state: ResearchState = {
        "symbol": symbol or "未指定标的",
        "question": question,
        "run_type": run_type,
        "market_context": context,
    }
    graph = build_research_graph(model)
    async for update in graph.astream(state, stream_mode="updates"):
        for node, delta in update.items():
            field = NODE_FIELD.get(node)
            content = delta.get(field) if field else None
            if content:
                yield {"node": node, "content": content}

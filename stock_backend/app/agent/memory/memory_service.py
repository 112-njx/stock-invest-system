"""本地记忆服务：LLM 抽取关键事实 → 写记忆文件 + ChromaDB 向量化 → memory_chunks/user_memory_files 登记 → 相似度检索。

借鉴 TradingAgents-CN 记忆分层：会话（短期）→ 抽取事实（中期）→ 向量库（长期）。
默认本地 embedding（store.HashEmbedding），后续可换；记忆文件保持人类可读。
"""

import json
import logging
import re
import uuid

from sqlalchemy.orm import Session

from app.agent.memory import store
from app.core.config import get_settings
from app.repositories import agent_repo
from app.services.llm import LLMService, get_llm_service

logger = logging.getLogger(__name__)
settings = get_settings()

_EXTRACT_PROMPT = """你是记忆抽取助手。从下面的对话中抽取「值得长期复用」的用户交易事实（交易体系、交易规则、风险偏好、关键持仓、操作习惯），忽略闲聊与一次性分析结论。

输出严格的 JSON 数组（不要 markdown 代码块），每个元素格式：
{"content": "一句话事实", "type": "rule|preference|experience|strategy", "importance": 1-10}
要求：
- importance 表示对后续决策的价值，1-10 分，低于 5 分不要输出
- 只保留可复用于未来决策的事实
- 没有可抽取事实时输出 []

对话：
[用户]: {user_msg}

[助手]: {assistant_msg}
"""

_FACT_TYPES = {"rule", "preference", "experience", "strategy"}


def _parse_facts(text: str) -> list[dict]:
    """解析 LLM 返回的 JSON 数组（容错去 markdown 围栏）。"""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.MULTILINE).strip()
    try:
        data = json.loads(t)
    except json.JSONDecodeError:
        # 容错：尝试提取第一个 [ ... ] 块
        m = re.search(r"\[.*\]", t, flags=re.DOTALL)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    facts = []
    for item in data:
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", "")).strip()
        ftype = str(item.get("type", "preference")).strip().lower()
        try:
            importance = int(item.get("importance", 1))
        except (TypeError, ValueError):
            importance = 1
        if content and ftype in _FACT_TYPES and importance >= settings.MEMORY_IMPORTANCE_MIN:
            facts.append({"content": content, "type": ftype, "importance": importance})
    return facts


async def aextract_facts(user_msg: str, assistant_msg: str, llm_svc: LLMService | None = None) -> list[dict]:
    """从一次对话抽取可入库记忆（供聊天流程生成结束后调用）；LLM 不可用/失败返回空，不影响主链路。"""
    llm_svc = llm_svc or get_llm_service()
    if not llm_svc.available:
        return []
    prompt = _EXTRACT_PROMPT.format(user_msg=user_msg[:1000], assistant_msg=assistant_msg[:2000])
    try:
        result = await llm_svc.ainvoke([{"role": "user", "content": prompt}])
    except Exception as e:  # noqa: BLE001
        logger.warning("memory extract failed: %s", e)
        return []
    return _parse_facts(result.text)


def save_memory(db: Session, user_id: int, source_type: str, source_id: int | None, facts: list[dict]) -> int:
    """保存抽取事实：写记忆文件 + ChromaDB 向量化 + memory_chunks/user_memory_files 登记。返回入库条数。"""
    saved = 0
    for fact in facts:
        try:
            vector_id = f"u{user_id}_{source_type}_{uuid.uuid4().hex[:12]}"
            fpath = store.append_to_memory_file(user_id, fact["type"], fact["content"], fact["importance"])
            store.add_chunk(user_id, vector_id, fact["content"], {"source_type": fact["type"], "source_id": source_id, "file_path": str(fpath)})
            agent_repo.add_memory_chunk(
                db, user_id, fact["type"], source_id, fact["content"], vector_id, str(fpath)
            )
            agent_repo.upsert_memory_file(db, user_id, str(fpath), fact["type"])
            saved += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("save_memory failed user=%s: %s", user_id, e)
    if saved:
        db.commit()
    return saved


def retrieve_memory(db: Session, user_id: int, query: str, top_k: int | None = None) -> str:
    """相似度检索 TopK → 格式化文本注入上下文。"""
    hits = store.search(user_id, query, top_k=top_k)
    if not hits:
        return ""
    lines = [f"- {h['content']}（来源:{h['source_type']}）" for h in hits]
    return "\n".join(lines)


def memory_tool(db: Session, user_id: int):
    """LangChain 工具：Agent 按需检索用户记忆（@tool 装饰器动态构造）。"""
    from langchain_core.tools import tool

    @tool("search_memory")
    def search_memory(query: str) -> dict:
        """检索用户的历史交易记忆（交易体系/规则/偏好），用于在回答中贴合用户的交易习惯。

        当问题涉及仓位管理、止损习惯、历史偏好时调用；query 为要检索的记忆主题（如"止损习惯"）。

        Args:
            query: 检索主题，例如 "止损习惯"
        """
        hits = store.search(user_id, query, top_k=settings.MEMORY_TOP_K)
        return {"results": hits}

    return search_memory

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
{{"content": "一句话事实", "type": "rule|preference|experience|strategy", "importance": 1-10}}
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
    """保存抽取事实：写记忆文件 + ChromaDB 向量化 + memory_chunks/user_memory_files 登记。

    阶段六 6.3 去重合并：新记忆写入前与同用户已有记忆算余弦相似度，>0.85 时更新已有记忆
    （内容取较新表述、importance 取最大值），不新增。返回入库条数（不含合并条数）。
    """
    saved = 0
    merged = 0
    for fact in facts:
        try:
            importance = int(fact.get("importance", 5))
            dup = store.find_duplicate(user_id, fact["content"], threshold=0.85)
            if dup is not None:
                # 合并：更新已有记忆内容 + importance 取最大，不新增
                new_importance = max(importance, int((dup["meta"] or {}).get("importance", 5)))
                meta = {**(dup["meta"] or {}), "importance": new_importance}
                store.update_chunk(user_id, dup["chunk_id"], fact["content"], meta)
                agent_repo.update_memory_chunk_by_vector(
                    db, user_id, dup["chunk_id"], content=fact["content"], importance=new_importance
                )
                store.append_to_memory_file(user_id, fact["type"], f"{fact['content']}（合并更新）", new_importance)
                merged += 1
                continue

            vector_id = f"u{user_id}_{source_type}_{uuid.uuid4().hex[:12]}"
            fpath = store.append_to_memory_file(user_id, fact["type"], fact["content"], importance)
            store.add_chunk(
                user_id,
                vector_id,
                fact["content"],
                {"source_type": fact["type"], "source_id": source_id, "file_path": str(fpath), "importance": importance},
            )
            agent_repo.add_memory_chunk(
                db, user_id, fact["type"], source_id, fact["content"], vector_id, str(fpath), importance=importance
            )
            agent_repo.upsert_memory_file(db, user_id, str(fpath), fact["type"])
            saved += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("save_memory failed user=%s: %s", user_id, e)
    if saved or merged:
        db.commit()
    return saved


def retrieve_memory(db: Session, user_id: int, query: str, top_k: int | None = None) -> str:
    """相似度检索 TopK → 格式化文本注入上下文。"""
    hits = store.search(user_id, query, top_k=top_k)
    if not hits:
        return ""
    lines = [f"- {h['content']}（来源:{h['source_type']}）" for h in hits]
    return "\n".join(lines)


def cleanup_expired_memories(db: Session, *, importance_below: int = 3, days: int = 30) -> int:
    """清理低重要性且超过保留期的记忆（PG + ChromaDB），返回删除条数（阶段六 6.2）。"""
    from datetime import UTC, datetime, timedelta

    older_than = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)  # naive UTC 对齐 DB 列
    chunks = agent_repo.list_low_importance_chunks(db, importance_below=importance_below, older_than=older_than)
    deleted = 0
    for c in chunks:
        if c.vector_id:
            store.delete_chunk(c.user_id, c.vector_id)
        agent_repo.delete_memory_chunk_by_id(db, c.user_id, c.id)
        deleted += 1
    if deleted:
        db.commit()
    return deleted


def list_facts(
    db: Session, user_id: int, importance_min: int | None = None, page: int = 1, size: int = 20
) -> tuple[list, int]:
    """分页返回用户记忆（阶段六 6.4），返回 (rows, total)。"""
    page = max(1, page)
    size = max(1, min(size, 100))
    rows = agent_repo.list_memory_chunks(db, user_id, importance_min=importance_min, offset=(page - 1) * size, limit=size)
    total = agent_repo.count_memory_chunks(db, user_id, importance_min)
    return rows, total


def delete_fact(db: Session, user_id: int, fact_id: int) -> bool:
    """删除单条记忆（同步删 ChromaDB 向量 + PG 记录，阶段六 6.4）。"""
    chunk = agent_repo.get_memory_chunk_by_id(db, user_id, fact_id)
    if chunk is None:
        return False
    if chunk.vector_id:
        store.delete_chunk(user_id, chunk.vector_id)
    agent_repo.delete_memory_chunk_by_id(db, user_id, fact_id)
    db.commit()
    return True


def clear_all_facts(db: Session, user_id: int) -> int:
    """清空全部记忆（重建 ChromaDB collection + 删 PG 记录 + 删本地记忆文件，阶段六 6.4）。"""
    import shutil

    store.delete_collection(user_id)  # 重建 collection
    deleted = agent_repo.delete_all_memory_chunks(db, user_id)
    agent_repo.delete_all_memory_files(db, user_id)
    db.commit()
    try:
        d = store.memory_dir(user_id)
        shutil.rmtree(d, ignore_errors=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("clear memory dir failed user=%s: %s", user_id, e)
    return deleted


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

"""本地记忆存储：memory_chunks（PostgreSQL + pgvector）向量读写与检索 + 人类可读记忆文件。

G21（P1-12b）：由 ChromaDB PersistentClient 迁移到 SQLAlchemy + pgvector，检索全链路下推 SQL。
- 向量列 `memory_chunks.embedding`（vector(384)）+ `embedding_kind`（hash/minilm）行级过滤，
  取代原 per-user collection（`user_memory_{user_id}[_minilm]`）。
- **召回口径锁定（G31 验收基准，勿改）**：`similarity = 1 - 余弦距离`，
  `score = similarity × 0.7 + (importance / 10) × 0.3`，去重阈值 `similarity > 0.85`。
  旧实现 Chroma 默认 `hnsw:space=l2` 返回平方 L2 距离，向量已 L2 归一（L2² = 2 - 2cos），
  旧式 `1 - distance/2` 化简即 `cos`，与新式 `1 - 余弦距离` 数学等价 —— G31 TopK 对比依赖此等价性。
- G31 已完成存量回填与 TopK 召回对比验证（4/4 一致），Chroma 依赖、`data/chroma/` 目录与
  `CHROMA_DIR` / `MEMORY_DUAL_WRITE` 配置均已下线，PG 为向量存储唯一真源。
- 人类可读记忆文件（M 区「记忆文件」可打开）保持原样，不随向量存储迁移改变。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session

from app.agent.memory.embedding import get_embedding
from app.core.config import get_settings
from app.models.agent import MemoryChunk
from app.repositories import agent_repo

logger = logging.getLogger(__name__)
settings = get_settings()

# 检索加权系数（与旧实现一致，G31 对比基准）
SIMILARITY_WEIGHT = 0.7
IMPORTANCE_WEIGHT = 0.3
# 去重合并阈值（余弦相似度）
DEDUP_THRESHOLD = 0.85


def embedding_kind() -> str:
    """当前 embedding 类型（hash / minilm），作为 embedding_kind 列取值与行级过滤条件。"""
    return get_embedding().kind


# ---- 向量计算 ----
def embed_text(text: str) -> np.ndarray:
    """单条文本向量化（归一向量，用于余弦相似度检索/去重）。"""
    return np.asarray(get_embedding()([text])[0], dtype=np.float32)


def _usable(vec: np.ndarray) -> bool:
    """零向量无法定义余弦相似度（pgvector 返回 NaN），直接判为不可用。"""
    return bool(np.any(vec))


# ---- 向量写入/检索（memory_chunks 行级增删改）----
def add_chunk(db: Session, user_id: int, chunk_id: str, content: str, meta: dict) -> MemoryChunk:
    """写入一条记忆切片：content + embedding + embedding_kind 一次落库（G31 回填的对照基准）。"""
    meta = meta or {}
    vec = embed_text(content)
    row = agent_repo.add_memory_chunk(
        db,
        user_id,
        str(meta.get("source_type") or ""),
        meta.get("source_id"),
        content,
        chunk_id,
        meta.get("file_path"),
        importance=int(meta.get("importance", 5)),
    )
    row.embedding = vec.tolist()
    row.embedding_kind = embedding_kind()
    db.flush()
    return row


def update_chunk(db: Session, user_id: int, chunk_id: str, content: str, meta: dict) -> bool:
    """更新已有切片（内容变更触发重新向量化），供记忆去重合并使用。"""
    meta = meta or {}
    row = agent_repo.get_memory_chunk_by_vector(db, user_id, chunk_id)
    if row is None:
        logger.warning("update_chunk miss user=%s id=%s", user_id, chunk_id)
        return False
    row.content = content
    if meta.get("importance") is not None:
        row.importance = int(meta["importance"])
    row.embedding = embed_text(content).tolist()
    row.embedding_kind = embedding_kind()
    db.flush()
    return True


def delete_chunk(db: Session, user_id: int, chunk_id: str) -> bool:
    """按 vector_id 删除切片。"""
    row = agent_repo.get_memory_chunk_by_vector(db, user_id, chunk_id)
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def delete_chunk_by_id(db: Session, user_id: int, fact_id: int) -> bool:
    """按主键删除切片（记忆管理 API / 过期清理用）。"""
    row = agent_repo.get_memory_chunk_by_id(db, user_id, fact_id)
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def delete_collection(db: Session, user_id: int) -> int:
    """清空用户全部记忆切片（等价于旧实现删除 per-user collection）。"""
    deleted = agent_repo.delete_all_memory_chunks(db, user_id)
    db.flush()
    return deleted


# ---- 检索 ----
def _weighted_score(distance: float, importance: int) -> float:
    """检索加权：相似度×0.7 + 重要性×0.3。

    `distance` 为**余弦距离**（pgvector `<=>`，即 1 - 余弦相似度），故 `similarity = 1 - distance`。
    与旧实现（Chroma 平方 L2 距离，`1 - distance/2`）在归一向量下数学等价 —— G31 对比基准。
    """
    similarity = max(0.0, 1.0 - distance)
    return similarity * SIMILARITY_WEIGHT + (importance / 10.0) * IMPORTANCE_WEIGHT


def _candidate_limit(k: int) -> int:
    """多取候选供加权重排（与旧实现一致：max(k, min(3k, 30))）。"""
    return max(k, min(k * 3, 30))


def search(db: Session, user_id: int, query: str, top_k: int | None = None) -> list[dict]:
    """加权检索 TopK：先按余弦距离取候选，再按 相似度×0.7 + 重要性×0.3 重排，返回含 importance/score。

    两段式（候选按距离取 → 外层按 score 排序）与旧 Chroma 实现逐步对应，保证召回口径一致。
    `user_id` + `embedding_kind` 行级过滤替代 per-user collection，实现多租户隔离与向量空间隔离。
    """
    k = top_k or settings.MEMORY_TOP_K
    fetch = _candidate_limit(k)
    qvec = embed_text(query)
    if not _usable(qvec):
        return []

    dist = MemoryChunk.embedding.cosine_distance(qvec.tolist())
    similarity = func.greatest(0.0, 1.0 - dist)
    score = similarity * SIMILARITY_WEIGHT + (cast(MemoryChunk.importance, Float) / 10.0) * IMPORTANCE_WEIGHT

    candidates = (
        select(MemoryChunk.id.label("id"), dist.label("distance"), score.label("score"))
        .where(
            MemoryChunk.user_id == user_id,
            MemoryChunk.embedding.is_not(None),
            MemoryChunk.embedding_kind == embedding_kind(),
        )
        .order_by(dist)
        .limit(fetch)
        .subquery()
    )
    stmt = (
        select(MemoryChunk, candidates.c.distance, candidates.c.score)
        .join(candidates, MemoryChunk.id == candidates.c.id)
        .order_by(candidates.c.score.desc())
        .limit(k)
    )
    hits: list[dict] = []
    for chunk, distance, score_value in db.execute(stmt).all():
        hits.append(
            {
                "chunk_id": chunk.vector_id,
                "content": chunk.content,
                "distance": float(distance),
                "importance": int(chunk.importance),
                "score": float(score_value),
                "source_type": chunk.source_type or "",
                "source_id": chunk.source_id,
                "file_path": chunk.file_path or "",
            }
        )
    return hits


def find_duplicate(db: Session, user_id: int, content: str, threshold: float = DEDUP_THRESHOLD) -> dict | None:
    """查找与 content 余弦相似度 > threshold 的已有记忆（阶段六 6.3 去重合并）。

    取相似度最高的一条，超阈值才返回；`embedding_kind` 隔离避免 hash/minilm 向量混算。
    """
    qvec = embed_text(content)
    if not _usable(qvec):
        return None
    similarity = 1.0 - MemoryChunk.embedding.cosine_distance(qvec.tolist())
    stmt = (
        select(MemoryChunk, similarity.label("similarity"))
        .where(
            MemoryChunk.user_id == user_id,
            MemoryChunk.embedding.is_not(None),
            MemoryChunk.embedding_kind == embedding_kind(),
        )
        .order_by(similarity.desc())
        .limit(1)
    )
    row = db.execute(stmt).first()
    if row is None:
        return None
    chunk, sim = row
    if sim is None or float(sim) <= threshold:
        return None
    return {
        "chunk_id": chunk.vector_id,
        "content": chunk.content,
        "meta": {
            "source_type": chunk.source_type,
            "source_id": chunk.source_id,
            "file_path": chunk.file_path,
            "importance": chunk.importance,
        },
        "similarity": float(sim),
    }


# ---- 人类可读记忆文件 ----
def memory_dir(user_id: int) -> Path:
    d = Path(settings.MEMORY_DIR) / str(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def append_to_memory_file(user_id: int, source_type: str, content: str, importance: int) -> Path:
    """把一条记忆追加到用户记忆文件（markdown 人类可读）。"""
    d = memory_dir(user_id)
    safe_type = re.sub(r"[^\w一-鿿-]", "_", source_type)
    fpath = d / f"{safe_type}.md"
    stamp = __import__("datetime").datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
    with fpath.open("a", encoding="utf-8") as f:
        f.write(f"- [{stamp}] (重要度{importance}) {content}\n")
    return fpath

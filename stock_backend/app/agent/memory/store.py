"""本地记忆存储：ChromaDB 持久化（可插拔 embedding：MiniLM 语义 / hash 回退）+ 人类可读记忆文件。

借鉴 TradingAgents-CN 记忆分层：长期记忆走本地向量库；文件保持人类可读（M 区「记忆文件」可打开）。
Embedding 由 `embedding.get_embedding()` 按配置选择（阶段六 6.1），collection 名按 embedding 类型隔离，
避免 hash 与 MiniLM 向量混用导致检索失真。
"""

import logging
import re
from pathlib import Path

import chromadb
import numpy as np

from app.agent.memory.embedding import get_embedding
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


_client_instance: chromadb.PersistentClient | None = None
_client_path: str | None = None


def _client() -> chromadb.PersistentClient:
    """进程内按路径缓存的 PersistentClient：同一 client 上写入即时落盘（新建连接会丢未刷盘数据）。"""
    global _client_instance, _client_path
    if _client_instance is None or _client_path != settings.CHROMA_DIR:
        _client_instance = chromadb.PersistentClient(path=settings.CHROMA_DIR)
        _client_path = settings.CHROMA_DIR
    return _client_instance


def _collection_name(user_id: int) -> str:
    """collection 名按 embedding 类型隔离：hash 保持 `user_memory_{id}`（兼容旧数据），minilm 加后缀。"""
    kind = get_embedding().kind
    suffix = "" if kind == "hash" else f"_{kind}"
    return f"user_memory_{user_id}{suffix}"


def collection(user_id: int):
    """按用户取 collection（重开须传同一 embedding 函数）。"""
    return _client().get_or_create_collection(_collection_name(user_id), embedding_function=get_embedding())


# ---- 向量写入/检索 ----
def add_chunk(user_id: int, chunk_id: str, content: str, meta: dict) -> None:
    # ChromaDB 元数据不支持 None 值，过滤后写入
    safe_meta = {k: v for k, v in (meta or {}).items() if v is not None}
    try:
        collection(user_id).add(ids=[chunk_id], documents=[content], metadatas=[safe_meta])
    except Exception:  # noqa: BLE001
        logger.warning("chroma add failed user=%s id=%s", user_id, chunk_id)


def update_chunk(user_id: int, chunk_id: str, content: str, meta: dict) -> None:
    """更新已有 chunk（内容变更触发重新向量化），供记忆去重合并使用。"""
    safe_meta = {k: v for k, v in (meta or {}).items() if v is not None}
    try:
        collection(user_id).update(ids=[chunk_id], documents=[content], metadatas=[safe_meta])
    except Exception:  # noqa: BLE001
        logger.warning("chroma update failed user=%s id=%s", user_id, chunk_id)


def delete_chunk(user_id: int, chunk_id: str) -> None:
    try:
        collection(user_id).delete(ids=[chunk_id])
    except Exception:  # noqa: BLE001
        logger.warning("chroma delete failed user=%s id=%s", user_id, chunk_id)


def delete_collection(user_id: int) -> None:
    """清空用户记忆时删除整个 collection（重建 collection）。"""
    name = _collection_name(user_id)
    try:
        _client().delete_collection(name)
    except Exception:  # noqa: BLE001
        logger.warning("chroma delete collection failed user=%s", user_id)


def _weighted_score(distance: float, importance: int) -> float:
    """检索加权（阶段六 6.2）：相似度×0.7 + 重要性×0.3。"""
    similarity = max(0.0, 1.0 - distance / 2.0)  # 距离（余弦/L2 归一向量均 ≤2）→ 相似度 [0,1]
    return similarity * 0.7 + (importance / 10.0) * 0.3


def _to_list(x) -> list:
    """ChromaDB 返回可能是 list / numpy array，统一转 Python list。"""
    if x is None:
        return []
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, list):
        return x
    return [x]


def embed_text(text: str) -> np.ndarray:
    """单条文本向量化（归一向量，用于去重余弦相似度）。"""
    return np.asarray(get_embedding()([text])[0], dtype=np.float32)


def find_duplicate(user_id: int, content: str, threshold: float = 0.85) -> dict | None:
    """查找与 content 余弦相似度 > threshold 的已有记忆（阶段六 6.3 去重合并）。"""
    vec = embed_text(content)
    try:
        r = collection(user_id).get(include=["embeddings", "documents", "metadatas"])
    except Exception:  # noqa: BLE001
        logger.warning("chroma get failed user=%s", user_id)
        return None
    ids = _to_list(r.get("ids"))
    embs = _to_list(r.get("embeddings"))
    docs = _to_list(r.get("documents"))
    metas = _to_list(r.get("metadatas"))
    best: dict | None = None
    best_sim = 0.0
    for cid, e, doc, meta in zip(ids, embs, docs, metas, strict=False):
        if e is None or not doc:
            continue
        sim = float(np.dot(vec, np.asarray(e)))  # 向量已归一，点积即余弦相似度
        if sim > best_sim:
            best_sim = sim
            best = {"chunk_id": cid, "content": doc, "meta": meta or {}}
    if best is not None and best_sim > threshold:
        best["similarity"] = best_sim
        return best
    return None


def search(user_id: int, query: str, top_k: int | None = None) -> list[dict]:
    """加权检索 TopK：先取候选再按 相似度×0.7 + 重要性×0.3 重排，返回含 importance/score。"""
    k = top_k or settings.MEMORY_TOP_K
    fetch = max(k, min(k * 3, 30))  # 多取候选供重排
    try:
        r = collection(user_id).query(query_texts=[query], n_results=fetch)
    except Exception:  # noqa: BLE001
        logger.warning("chroma query failed user=%s", user_id)
        return []
    hits: list[dict] = []
    ids = (r.get("ids") or [[]])[0]
    dists = (r.get("distances") or [[]])[0]
    metas = (r.get("metadatas") or [[]])[0]
    docs = (r.get("documents") or [[]])[0]
    for cid, dist, meta, doc in zip(ids, dists, metas, docs, strict=False):
        importance = int((meta or {}).get("importance", 5))
        hits.append(
            {
                "chunk_id": cid,
                "content": doc,
                "distance": float(dist),
                "importance": importance,
                "score": _weighted_score(float(dist), importance),
                "source_type": (meta or {}).get("source_type", ""),
                "source_id": (meta or {}).get("source_id"),
                "file_path": (meta or {}).get("file_path", ""),
            }
        )
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:k]


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

"""本地记忆存储：ChromaDB 持久化（离线 hash embedding）+ 人类可读记忆文件。

借鉴 TradingAgents-CN 记忆分层：长期记忆走本地向量库；文件保持人类可读（M 区「记忆文件」可打开）。
"""

import hashlib
import logging
import re
from pathlib import Path

import chromadb
import numpy as np
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class HashEmbedding(EmbeddingFunction[Documents]):
    """离线确定性 embedding：字符 n-gram 哈希到固定维度，无需下载模型。

    满足「默认本地 embedding」；后续可替换为 ONNX MiniLM（联网下载一次）等更强模型。
    """

    def __init__(self, dim: int = 384):
        self.dim = dim

    def name(self) -> str:
        return f"local-hash-{self.dim}"

    def get_config(self) -> dict:
        return {"dim": self.dim}

    def _embed(self, text: str) -> list[float]:
        vec = np.zeros(self.dim, dtype=np.float32)
        t = text.lower()
        for n in (1, 2, 3):
            for i in range(len(t) - n + 1):
                h = int(hashlib.md5(t[i : i + n].encode("utf-8")).hexdigest(), 16)
                idx = h % self.dim
                vec[idx] += 1.0 if (h >> 8) % 2 == 0 else -1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.tolist()

    def __call__(self, input: Documents) -> Embeddings:
        if isinstance(input, str):
            input = [input]
        return [self._embed(t) for t in input]


_client_instance: chromadb.PersistentClient | None = None
_client_path: str | None = None


def _client() -> chromadb.PersistentClient:
    """进程内按路径缓存的 PersistentClient：同一 client 上写入即时落盘（新建连接会丢未刷盘数据）。"""
    global _client_instance, _client_path
    if _client_instance is None or _client_path != settings.CHROMA_DIR:
        _client_instance = chromadb.PersistentClient(path=settings.CHROMA_DIR)
        _client_path = settings.CHROMA_DIR
    return _client_instance


def collection(user_id: int):
    """按用户取 collection（重开须传同一 embedding 函数）。"""
    return _client().get_or_create_collection(f"user_memory_{user_id}", embedding_function=HashEmbedding())


# ---- 向量写入/检索 ----
def add_chunk(user_id: int, chunk_id: str, content: str, meta: dict) -> None:
    # ChromaDB 元数据不支持 None 值，过滤后写入
    safe_meta = {k: v for k, v in (meta or {}).items() if v is not None}
    try:
        collection(user_id).add(ids=[chunk_id], documents=[content], metadatas=[safe_meta])
    except Exception:  # noqa: BLE001
        logger.warning("chroma add failed user=%s id=%s", user_id, chunk_id)


def delete_chunk(user_id: int, chunk_id: str) -> None:
    try:
        collection(user_id).delete(ids=[chunk_id])
    except Exception:  # noqa: BLE001
        logger.warning("chroma delete failed user=%s id=%s", user_id, chunk_id)


def search(user_id: int, query: str, top_k: int | None = None) -> list[dict]:
    """相似度检索 TopK，返回 {content, distance, source_type, source_id, file_path}。"""
    k = top_k or settings.MEMORY_TOP_K
    try:
        r = collection(user_id).query(query_texts=[query], n_results=k)
    except Exception:  # noqa: BLE001
        logger.warning("chroma query failed user=%s", user_id)
        return []
    out: list[dict] = []
    ids = (r.get("ids") or [[]])[0]
    dists = (r.get("distances") or [[]])[0]
    metas = (r.get("metadatas") or [[]])[0]
    docs = (r.get("documents") or [[]])[0]
    for cid, dist, meta, doc in zip(ids, dists, metas, docs, strict=False):
        out.append(
            {
                "chunk_id": cid,
                "content": doc,
                "distance": float(dist),
                "source_type": (meta or {}).get("source_type", ""),
                "source_id": (meta or {}).get("source_id"),
                "file_path": (meta or {}).get("file_path", ""),
            }
        )
    return out


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

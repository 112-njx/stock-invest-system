"""阶段六 6.1：ChromaDB collection 重建脚本（HashEmbedding → MiniLM 重新向量化）。

HashEmbedding 的向量与 MiniLM 不兼容，切换 EMBEDDING_MODEL=minilm 后需重建。
记忆原文在 memory_chunks 表保留，可重新向量化（不需重新抽取）。

用法（确保 .env 已设 EMBEDDING_MODEL=minilm）：
    .venv/Scripts/python.exe scripts/rebuild_embeddings.py
"""

import logging
import sys

from sqlalchemy import select

from app.agent.memory import store
from app.agent.memory.embedding import get_embedding
from app.core.config import get_settings
from app.models.agent import MemoryChunk
from app.utils.db import get_session

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("rebuild_embeddings")


def main() -> int:
    settings = get_settings()
    emb = get_embedding()
    if emb.kind != "minilm":
        logger.warning("当前 EMBEDDING_MODEL=%s（非 minilm），无需重建，跳过。", settings.EMBEDDING_MODEL)
        return 0

    db = get_session()
    try:
        chunks = list(db.scalars(select(MemoryChunk).order_by(MemoryChunk.user_id, MemoryChunk.id)))
    finally:
        db.close()

    by_user: dict[int, list[MemoryChunk]] = {}
    for c in chunks:
        by_user.setdefault(c.user_id, []).append(c)

    logger.info("共 %d 个用户、%d 条记忆待重建", len(by_user), len(chunks))
    for user_id, rows in by_user.items():
        store.delete_collection(user_id)  # 删除旧 minilm collection（如存在）
        for c in rows:
            meta = {"source_type": c.source_type, "source_id": c.source_id, "file_path": c.file_path}
            if getattr(c, "importance", None) is not None:
                meta["importance"] = c.importance
            store.add_chunk(user_id, c.vector_id, c.content, meta)
        logger.info("用户 %d：重建 %d 条", user_id, len(rows))
    logger.info("重建完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())

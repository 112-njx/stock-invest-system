"""阶段六 6.1（G21 改写）：按当前 embedding 模型重新向量化 memory_chunks。

HashEmbedding 与 MiniLM 的向量空间不兼容，切换 EMBEDDING_MODEL 后需重建。
记忆原文在 memory_chunks.content 保留，可原地重新向量化（不需重新抽取）。

G21 后向量与原文同表（memory_chunks.embedding / embedding_kind），故重建即「按当前模型重算两列」，
不再需要删除/重建 collection。

用法（确保 .env 已设目标 EMBEDDING_MODEL）：
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
    kind = get_embedding().kind
    logger.info("当前 EMBEDDING_MODEL=%s（kind=%s）", settings.EMBEDDING_MODEL, kind)

    db = get_session()
    try:
        chunks = list(db.scalars(select(MemoryChunk).order_by(MemoryChunk.user_id, MemoryChunk.id)))
        total = len(chunks)
        logger.info("共 %d 条记忆待重新向量化", total)
        by_user: dict[int, int] = {}
        for c in chunks:
            c.embedding = store.embed_text(c.content).tolist()
            c.embedding_kind = kind
            by_user[c.user_id] = by_user.get(c.user_id, 0) + 1
        db.commit()
        for user_id, n in by_user.items():
            logger.info("用户 %d：重建 %d 条", user_id, n)
    finally:
        db.close()
    logger.info("重建完成：%d 条", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())

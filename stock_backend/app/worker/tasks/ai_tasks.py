"""AI 队列 Celery 任务（阶段六 6.2：低重要性记忆清理）。"""

import logging

from app.agent.memory import memory_service
from app.utils.db import get_session
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="app.worker.tasks.ai_tasks.memory_cleanup")
def memory_cleanup(self) -> int:
    """每日凌晨清理：删除重要性 < 3 且创建超过 30 天的记忆（PG + ChromaDB）。"""
    db = get_session()
    try:
        deleted = memory_service.cleanup_expired_memories(db, importance_below=3, days=30)
        logger.info("memory_cleanup done, deleted=%d", deleted)
        return deleted
    except Exception:  # noqa: BLE001
        logger.exception("memory_cleanup failed")
        raise
    finally:
        db.close()

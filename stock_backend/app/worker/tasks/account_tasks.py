"""账户生命周期任务（G18）：扫描并硬删超过 30 天宽限期的已注销账户。

硬删为不可逆操作，任务只处理 `deleted_at <= now - 30d` 的行；
DB 层 11 张关联表均为 ON DELETE CASCADE，另清理记忆目录与导出文件。
"""

import logging

from app.core.request_id import get_request_id
from app.services import user_service
from app.utils.db import get_session
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.worker.tasks.account_tasks.purge_deleted_accounts")
def purge_deleted_accounts() -> dict:
    """每日扫描并硬删到期账户（beat 调度）。"""
    from app.repositories import ops_repo

    db = get_session()
    try:
        purged = user_service.purge_expired_deleted_accounts(db)
        if purged:
            logger.info("purged %s expired deleted accounts", purged)
        ops_repo.log_task(db, "account_purge", "beat", "success", f"purged={purged}", request_id=get_request_id())
        db.commit()
        return {"purged": purged}
    except Exception as exc:  # noqa: BLE001
        logger.exception("purge deleted accounts failed")
        db.rollback()
        try:
            ops_repo.log_task(
                db, "account_purge", "beat", "failed", str(exc), request_id=get_request_id()
            )
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        raise
    finally:
        db.close()

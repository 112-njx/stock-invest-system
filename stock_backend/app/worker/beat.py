"""Celery Beat 调度：增量同步（每日收盘后）+ 实时轮询（交易时段，任务内自判）。"""

from celery.schedules import crontab

from app.core.config import get_settings


def build_beat_schedule() -> dict:
    settings = get_settings()
    return {
        "kline-incremental-daily": {
            "task": "app.worker.tasks.sync_tasks.kline_incremental",
            "schedule": crontab(hour=settings.SYNC_INCREMENTAL_HOUR, minute=settings.SYNC_INCREMENTAL_MINUTE),
        },
        "realtime-poll": {
            "task": "app.worker.tasks.sync_tasks.realtime_poll",
            "schedule": settings.REALTIME_POLL_INTERVAL,  # 秒
        },
        "provider-probe": {
            "task": "app.worker.tasks.sync_tasks.provider_probe",
            "schedule": settings.PROVIDER_PROBE_INTERVAL,  # 秒：探测熔断中 Provider
        },
        "catalog-sync-daily": {
            "task": "app.worker.tasks.sync_tasks.catalog_sync",
            "schedule": crontab(hour=3, minute=0),  # 每日凌晨 3:00 全量目录同步
        },
        "memory-cleanup-daily": {
            "task": "app.worker.tasks.ai_tasks.memory_cleanup",
            "schedule": crontab(hour=4, minute=0),  # 每日凌晨 4:00 低重要性记忆清理（阶段六 6.2）
        },
        "export-cleanup-daily": {
            "task": "app.worker.tasks.export_tasks.cleanup_expired_exports",
            "schedule": crontab(hour=4, minute=30),  # G17：每日凌晨 4:30 清理过期导出文件（24h TTL）
        },
        "account-purge-daily": {
            "task": "app.worker.tasks.account_tasks.purge_deleted_accounts",
            "schedule": crontab(hour=4, minute=45),  # G18：每日凌晨 4:45 硬删超 30 天宽限期的已注销账户
        },
        # ---- G05（P1-1）备份与灾难恢复：全部排在业务空闲窗口 ----
        "backup-daily": {
            "task": "app.worker.tasks.backup_tasks.backup_daily",
            "schedule": crontab(hour=2, minute=0),  # 每日 02:00 全量备份（pg_dump -Fc + 文件镜像 + 保留期清理）
        },
        "backup-base-weekly": {
            "task": "app.worker.tasks.backup_tasks.backup_base_weekly",
            "schedule": crontab(day_of_week=0, hour=2, minute=45),  # 每周日 02:45 物理基础备份（PITR 基线）
        },
        "backup-offsite-daily": {
            "task": "app.worker.tasks.backup_tasks.offsite_sync_daily",
            "schedule": crontab(hour=2, minute=30),  # 每日 02:30 异地同步（rclone → 对象存储）
        },
        "backup-verify-weekly": {
            "task": "app.worker.tasks.backup_tasks.verify_backup_weekly",
            "schedule": crontab(day_of_week=0, hour=3, minute=30),  # 每周日 03:30 恢复演练（避开 03:00 catalog_sync）
        },
    }

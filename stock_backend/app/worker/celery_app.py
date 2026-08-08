"""Celery 应用：三队列（sync 行情 / backtest 回测 / ai AI），Beat 调度配置。

任务模块通过 `@celery_app.task` 显式注册，worker 侧 autodiscover 自动加载；
调用方（API/脚本）导入任一任务模块即触发 set_default，.delay() 走本项目 broker。
"""

from celery import Celery

from app.core.config import get_settings

from .beat import build_beat_schedule

settings = get_settings()

celery_app = Celery("stock_backend")
celery_app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.TIMEZONE,  # beat 按本地时区触发（DB 内仍存 UTC）
    enable_utc=False,
    task_default_queue="sync",
    task_default_exchange="sync",
    task_default_routing_key="sync",
    task_routes={
        "app.worker.tasks.sync_tasks.*": {"queue": "sync"},
        "app.worker.tasks.backtest_tasks.*": {"queue": "backtest"},
        "app.worker.tasks.ai_tasks.*": {"queue": "ai"},
    },
    beat_schedule=build_beat_schedule(),
)

# 显式注册任务模块：worker 侧加载，API 侧 .delay() 使用同一注册表
from .tasks import ai_tasks, backtest_tasks, sync_tasks  # noqa: E402,F401

# 设为默认应用：任务 .delay() 走本项目 broker，而非默认 AMQP
celery_app.set_default()

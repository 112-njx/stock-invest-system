"""FastAPI 应用入口：`uvicorn app.main:app` 启动。"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.metrics import MetricsMiddleware
from app.core.request_id import RequestIDMiddleware
from app.services import user_service
from app.utils.db import get_session

settings = get_settings()
setup_logging(debug=settings.DEBUG)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动钩子：管理员晋升 + 固定指数缓存预热（均 best-effort，不阻断启动）。"""
    _startup_tasks()
    yield


def _startup_tasks() -> None:
    if settings.APP_ENV == "test":  # 测试环境跳过启动任务（避免预热/调度/监听干扰）
        return
    try:
        db = get_session()
        try:
            user_service.ensure_admins(db)  # ADMIN_USERNAMES → is_admin
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        logger.warning("startup ensure_admins failed (skip)", exc_info=True)
    try:  # 阶段一 1.1：固定指数缓存预热（best-effort，失败不阻断启动）
        from app.services import sync_service

        result = sync_service.warmup_fixed_indices_cache()
        logger.info("startup cache warmup: %s", result)
    except Exception:  # noqa: BLE001
        logger.warning("startup cache warmup failed (skip)", exc_info=True)
    try:  # 阶段二 2.2：启动市场监听线程（Redis pub/sub → WS 推送）
        import asyncio
        import threading

        from app.api.v1 import ws_market

        _market_loop = asyncio.new_event_loop()

        def _run_listener():
            asyncio.set_event_loop(_market_loop)
            ws_market._market_listener_loop(_market_loop)

        threading.Thread(target=_run_listener, name="ws-market-listener", daemon=True).start()
        logger.info("startup market ws listener started")
    except Exception:  # noqa: BLE001
        logger.warning("startup market ws listener failed (skip)", exc_info=True)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()

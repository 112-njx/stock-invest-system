"""运维端点：/health（存活）、/ready（DB/Redis 就绪）、/metrics（Prometheus）。"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.metrics import prometheus_response
from app.core.response import ok
from app.utils.db import engine
from app.utils.redis_client import get_redis_client

router = APIRouter(tags=["ops"])


@router.get("/health")
def health() -> dict:
    settings = get_settings()
    return ok(data={"status": "alive", "app": settings.APP_NAME, "env": settings.APP_ENV})


@router.get("/ready")
def ready() -> JSONResponse:
    checks = {"db": False, "redis": False}
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["db"] = True
    except Exception:
        pass
    try:
        checks["redis"] = bool(get_redis_client().ping())
    except Exception:
        pass
    is_ready = all(checks.values())
    body = ok(data=checks, msg="ready" if is_ready else "not ready")
    return JSONResponse(status_code=200 if is_ready else 503, content=body)


@router.get("/metrics")
def metrics():
    return prometheus_response()

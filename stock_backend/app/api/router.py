"""API 路由聚合：运维端点挂根路径，业务端点挂 /api/v1。"""

from fastapi import APIRouter

from .v1 import health, market

api_router = APIRouter()
api_router.include_router(health.router)  # /health /ready /metrics
api_router.include_router(market.router)  # /api/v1/symbols|kline|snapshot

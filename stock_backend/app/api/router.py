"""API 路由聚合：运维端点挂根路径，业务端点挂 /api/v1。"""

from fastapi import APIRouter

from .v1 import auth, health, indicators, market, support_resistance, users, watchlist

api_router = APIRouter()
api_router.include_router(health.router)  # /health /ready /metrics
api_router.include_router(market.router)  # /api/v1/symbols|kline|snapshot
api_router.include_router(auth.router)  # /api/v1/auth/register|login
api_router.include_router(users.router)  # /api/v1/users/me
api_router.include_router(watchlist.router)  # /api/v1/watchlist
api_router.include_router(support_resistance.router)  # /api/v1/support-resistance
api_router.include_router(indicators.router)  # /api/v1/indicators

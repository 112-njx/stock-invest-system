"""API 路由聚合：运维端点挂根路径，业务端点挂 /api/v1。"""

from fastapi import APIRouter

from .v1 import (
    agent_ops,
    agents,
    auth,
    backtest,
    chat,
    conversations,
    health,
    indicators,
    market,
    strategies,
    support_resistance,
    users,
    watchlist,
)

api_router = APIRouter()
api_router.include_router(health.router)  # /health /ready /metrics
api_router.include_router(market.router)  # /api/v1/symbols|kline|snapshot
api_router.include_router(auth.router)  # /api/v1/auth/register|login
api_router.include_router(users.router)  # /api/v1/users/me
api_router.include_router(watchlist.router)  # /api/v1/watchlist
api_router.include_router(support_resistance.router)  # /api/v1/support-resistance
api_router.include_router(indicators.router)  # /api/v1/indicators
api_router.include_router(conversations.router)  # /api/v1/conversations
api_router.include_router(chat.router)  # /api/v1/chat（SSE）
api_router.include_router(strategies.router)  # /api/v1/strategies
api_router.include_router(agents.router)  # /api/v1/agents
api_router.include_router(backtest.router)  # /api/v1/backtest
api_router.include_router(agent_ops.router)  # /api/v1/agent/runs、/api/v1/memory/files

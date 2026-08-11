"""Prometheus 指标采集中间件：API 吞吐 / 延迟 / 错误率。"""

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_COUNT = Counter("http_requests_total", "累计 HTTP 请求数", ["method", "path", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP 请求耗时（秒）", ["method", "path"])

# ---- LLM 调用指标（AI 核心功能可观测：调用次数/耗时/token，借鉴 QuantDinger AI 监控）----
LLM_CALLS = Counter("llm_calls_total", "LLM 调用次数（按状态 ok/failed）", ["status"])
LLM_DURATION = Histogram("llm_request_duration_seconds", "LLM 调用耗时（秒）", ["status"])
LLM_TOKENS = Counter("llm_tokens_total", "LLM token 用量（按种类 total/prompt/completion）", ["kind"])


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()
        REQUEST_LATENCY.labels(request.method, request.url.path).observe(time.perf_counter() - start)
        return response


def prometheus_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

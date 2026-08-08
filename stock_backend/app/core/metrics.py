"""Prometheus 指标采集中间件：API 吞吐 / 延迟 / 错误率。"""

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_COUNT = Counter("http_requests_total", "累计 HTTP 请求数", ["method", "path", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "HTTP 请求耗时（秒）", ["method", "path"])


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()
        REQUEST_LATENCY.labels(request.method, request.url.path).observe(time.perf_counter() - start)
        return response


def prometheus_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

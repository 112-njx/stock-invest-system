"""全链路 request-id：中间件生成并透传（响应头 / 日志 / Celery 任务）。"""

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """取当前上下文 request-id，供日志/任务透传；无则空串。"""
    return _request_id_var.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """为每个请求生成/透传 request-id，写入响应头与上下文。"""

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        token = _request_id_var.set(req_id)
        request.state.request_id = req_id
        try:
            response = await call_next(request)
        finally:
            _request_id_var.reset(token)
        response.headers["X-Request-ID"] = req_id
        return response

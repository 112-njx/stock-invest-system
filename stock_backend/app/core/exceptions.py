"""全局异常处理：统一返回 {code, msg, data}，异常记录日志。"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .response import fail

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """业务异常：status_code 为 HTTP 状态码，code 为业务码。"""

    def __init__(self, status_code: int = 400, code: int = 1, msg: str = "error"):
        self.status_code = status_code
        self.code = code
        self.msg = msg


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=fail(code=exc.code, msg=exc.msg))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=fail(code=exc.status_code, msg=str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        msg = "参数校验失败"
        if exc.errors():
            loc = ".".join(str(p) for p in exc.errors()[0].get("loc", []) if p not in ("body", "query", "path"))
            msg = f"{loc}: {exc.errors()[0].get('msg', '')}" if loc else str(exc.errors()[0].get("msg", msg))
        return JSONResponse(status_code=422, content=fail(code=422, msg=msg))

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error: %s", exc)
        return JSONResponse(status_code=500, content=fail(code=500, msg="服务器内部错误"))

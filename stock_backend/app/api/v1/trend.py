"""Read-only stockdb trend matrix endpoints."""

import json
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.services import stockdb_service as rd
from app.services import trend_service as trends

router = APIRouter(prefix="/api/v1/stockdb/trend", tags=["stockdb-trends"])


def _reply(request: Request, payload: dict) -> Response:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    etag = '"' + sha256(body).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache"}
    if etag in [item.strip().removeprefix("W/") for item in request.headers.get("if-none-match", "").split(",")]:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/json", headers=headers)


def _data(version: str | None = None) -> dict:
    try:
        return trends.current(version)
    except rd.StockDBError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/status")
def status() -> dict:
    trends.start()
    return trends.status()


@router.get("/overview")
def overview(request: Request, industry: Annotated[str, Query(max_length=24)] = "all") -> Response:
    data = _data()
    if industry not in {"all", "unknown", *(item["id"] for item in data["industries"])}:
        raise HTTPException(status_code=404, detail="找不到该申万一级行业")
    return _reply(request, trends.overview(data, industry))


@router.get("/columns")
def columns(request: Request, codes: Annotated[str, Query(max_length=100)],
            version: Annotated[str, Query(max_length=80)]) -> Response:
    data = _data(version)
    requested = list(dict.fromkeys(codes.split(",")))
    by_code = {stock["code"]: stock for stock in data["stocks"]}
    if len(requested) > 12 or any(code not in by_code for code in requested):
        raise HTTPException(status_code=422, detail="每次可查询一至十二只有效股票")
    return _reply(request, {"version": data["version"], "columns": {code: by_code[code] for code in requested}})


@router.post("/refresh")
def refresh() -> dict:
    return trends.refresh()

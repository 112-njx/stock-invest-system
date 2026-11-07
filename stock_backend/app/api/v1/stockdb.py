"""Versioned index workspace endpoints backed exclusively by local stockdb RD."""

from hashlib import sha256
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response
from pydantic import StringConstraints

from app.core.config import get_settings
from app.services import stockdb_cache as cache
from app.services import stockdb_service as rd

router = APIRouter(prefix=f"{get_settings().API_V1_PREFIX}/stockdb", tags=["stockdb"])
Category = Literal["sw1", "sw2", "sw3", "concept"]
Weight = Literal["equal", "float_mv", "amount", "volume", "total_mv"]
Code = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]


@router.get("/heatmap")
def heatmap() -> dict:
    from app.services.heatmap_service import snapshot
    try:
        return snapshot()
    except rd.StockDBError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _snapshot(version: str | None = None) -> rd.Snapshot:
    try:
        data = rd.snapshot()
    except rd.StockDBError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if version is not None and data.version != version:
        raise HTTPException(status_code=409, detail="本地数据版本已更新")
    return data


def _reply(request: Request, data: rd.Snapshot, build=None, identity: str = "",
           encoded: bytes | None = None) -> Response:
    key = request.url.path + "?" + request.url.query + identity
    if encoded is None:
        encoded = cache.response_bytes(data, key, build)
    etag = '"' + sha256(encoded).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": "private, no-cache", "X-StockDB-Version": data.version}
    candidates = [item.strip().removeprefix("W/") for item in request.headers.get("if-none-match", "").split(",")]
    if etag in candidates or "*" in candidates:
        return Response(status_code=304, headers=headers)
    return Response(encoded, media_type="application/json", headers=headers)


def _detail(data: rd.Snapshot, codes: list[str]) -> dict:
    return {"version": data.version, "members": data.members(codes), "count": len(codes),
            "indices": {weight: data.index(codes, weight) for weight in rd.WEIGHTS}}


@router.get("/home")
def home(request: Request) -> Response:
    data = _snapshot()
    # Share the startup-warmed response rather than re-encoding the first screen.
    encoded = cache.response_bytes(data, "home", lambda: cache.home(data))
    return _reply(request, data, encoded=encoded)


@router.get("/ranking")
def ranking(request: Request, category: Category = "sw1", weight: Weight = "equal") -> Response:
    data = _snapshot()
    return _reply(request, data, lambda: {
        "version": data.version, "date": data.dates[-1], "boards": cache.ranking(data, category, weight),
    })


@router.get("/charts")
def charts(request: Request, ids: Annotated[str, Query(max_length=600)],
           weight: Weight = "equal", version: str | None = None) -> Response:
    data = _snapshot(version)
    board_ids = list(dict.fromkeys(ids.split(",")))
    if len(board_ids) > 10 or any(code not in data.boards for code in board_ids):
        raise HTTPException(status_code=422, detail="每次最多查询十个有效板块")
    return _reply(request, data, lambda: {
        "version": data.version,
        "charts": {code: data.index(data.boards[code]["symbols"], weight) for code in board_ids},
    })


@router.get("/members/{board_id}")
def members(request: Request, board_id: Annotated[str, Path(max_length=24)],
            version: str | None = None, selected: str = "",
            order: Literal["return", "price", "code"] = "return", ascending: bool = False) -> Response:
    data = _snapshot(version)
    board = data.boards.get(board_id)
    if board is None:
        raise HTTPException(status_code=404, detail="找不到该板块")
    return _reply(request, data, lambda: {
        "version": data.version, **cache.member_bundle(data, board["symbols"], selected, order, ascending),
    })


@router.get("/status")
def status() -> dict:
    return cache.status()


@router.post("/refresh")
def refresh() -> dict:
    cache.refresh(force=True)
    return cache.status()


# Preserve existing contracts for previously loaded clients.
@router.get("/boards")
def boards(request: Request, category: Category = "sw1", weight: Weight = "equal") -> Response:
    data = _snapshot()
    return _reply(request, data, lambda: {"date": data.dates[-1], "boards": data.category(category, weight)})


@router.get("/boards/{board_id}")
def board_detail(request: Request, board_id: Annotated[str, Path(max_length=24)],
                 version: str | None = None) -> Response:
    data = _snapshot(version)
    board = data.boards.get(board_id)
    if board is None:
        raise HTTPException(status_code=404, detail="找不到该板块")
    return _reply(request, data, lambda: _detail(data, board["symbols"]))


@router.get("/stocks/{code}")
def stock(request: Request, code: Code, version: str | None = None) -> Response:
    data = _snapshot(version)
    result = data.stocks.get(code)
    if result is None:
        raise HTTPException(status_code=404, detail="本地库中没有这只股票的日 K")
    return _reply(request, data, lambda: {"version": data.version, "bars": result["bars"]})


@router.get("/stocks/{code}/minutes")
def stock_minutes(code: Code, date: Annotated[int, Query(ge=19000101, le=29991231)]) -> list:
    try:
        return rd.minutes(code, date)
    except rd.StockDBError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/equities')
def equities() -> dict:
    from app.services.equity_table import snapshot
    return snapshot()

"""Index blueprint endpoints backed exclusively by the configured stockdb instance."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field, StringConstraints

from app.core.config import get_settings
from app.services import stockdb_service as rd

router = APIRouter(prefix=f"{get_settings().API_V1_PREFIX}/stockdb", tags=["stockdb"])
Category = Literal["sw1", "sw2", "sw3", "concept"]
Weight = Literal["equal", "float_mv", "amount", "volume", "total_mv"]
Code = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]


class Constituents(BaseModel):
    codes: list[Code] = Field(min_length=1, max_length=1000)


def _snapshot() -> rd.Snapshot:
    try:
        return rd.snapshot()
    except rd.StockDBError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _detail(data: rd.Snapshot, codes: list[str]) -> dict:
    return {"members": data.members(codes), "count": len(codes),
            "indices": {weight: data.index(codes, weight) for weight in rd.WEIGHTS}}


@router.get("/boards")
def boards(category: Category = "sw1", weight: Weight = "equal") -> dict:
    data = _snapshot()
    return {"date": data.dates[-1], "boards": data.category(category, weight)}


@router.get("/boards/{board_id}")
def board_detail(board_id: Annotated[str, Path(max_length=24)]) -> dict:
    data = _snapshot()
    board = data.boards.get(board_id)
    if board is None:
        raise HTTPException(status_code=404, detail="找不到该板块")
    return _detail(data, board["symbols"])


@router.post("/custom")
def custom_index(body: Constituents) -> dict:
    return _detail(_snapshot(), list(dict.fromkeys(body.codes)))


@router.get("/stocks/{code}")
def stock(code: Code) -> dict:
    data = _snapshot()
    result = data.stocks.get(code)
    if result is None:
        raise HTTPException(status_code=404, detail="本地库中没有这只股票的日 K")
    return {"bars": result["bars"]}


@router.get("/stocks/{code}/minutes")
def stock_minutes(code: Code, date: Annotated[int, Query(ge=19000101, le=29991231)]) -> list:
    try:
        return rd.minutes(code, date)
    except rd.StockDBError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

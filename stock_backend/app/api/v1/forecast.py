"""Read the inputs of the next-candle prediction pipeline."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_read_db
from app.core.response import ok
from app.services.forecast_snapshot import build_snapshot

router = APIRouter(prefix="/api/v1/forecast", tags=["forecast"])


@router.get("/snapshot")
def snapshot(symbol: Annotated[str, Query(pattern=r"^[0-9]{6}$")], db: Session = Depends(get_read_db)) -> dict:
    return ok(data=build_snapshot(db, symbol))

"""Read the inputs of the next-candle prediction pipeline."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, StringConstraints
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_read_db
from app.core.response import ok
from app.models.user import User
from app.services import forecast_runs
from app.services.forecast_snapshot import build_snapshot

router = APIRouter(prefix="/api/v1/forecast", tags=["forecast"])
StockCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]
StockQuery = Annotated[str, Query(pattern=r"^[0-9]{6}$")]


class StartForecast(BaseModel):
    symbol: StockCode


class TrackForecast(StartForecast):
    enabled: bool


@router.get("/snapshot")
def snapshot(symbol: StockQuery, db: Session = Depends(get_read_db)) -> dict:
    return ok(data=build_snapshot(db, symbol))


@router.get("/runs")
def history(symbol: StockQuery, current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return ok(data=forecast_runs.history(db, current.id, symbol))


@router.post("/runs")
def run(payload: StartForecast, current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return ok(data=forecast_runs.start_manual(db, current.id, payload.symbol))


@router.put("/tracking")
def tracking(payload: TrackForecast, current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return ok(data={"tracking": forecast_runs.set_tracking(db, current.id, payload.symbol, payload.enabled)})

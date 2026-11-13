"""Read the inputs of the next-candle prediction pipeline."""

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, StringConstraints, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_read_db
from app.core.response import ok
from app.models.user import User
from app.data_providers.base import DAILY_SESSION_TZ
from app.services import forecast_replay, forecast_runs
from app.services.forecast_snapshot import build_snapshot

router = APIRouter(prefix="/api/v1/forecast", tags=["forecast"])
StockCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]
StockQuery = Annotated[str, Query(pattern=r"^[0-9]{6}$")]


class StartForecast(BaseModel):
    symbol: StockCode


class TrackForecast(StartForecast):
    enabled: bool


class ReplayForecast(StartForecast):
    end: date | None = None
    samples: int = Field(default=5, ge=1, le=10)
    mode: Literal["reconstructed", "archived"] = "reconstructed"

    @field_validator("end")
    @classmethod
    def valid_end(cls, value):
        if value is not None and not date(1991, 1, 1) <= value <= datetime.now(DAILY_SESSION_TZ).date():
            raise ValueError("回放截止日期超出范围")
        return value


@router.get("/snapshot")
def snapshot(symbol: StockQuery, db: Session = Depends(get_read_db)) -> dict:
    return ok(data=build_snapshot(db, symbol))


@router.get("/runs")
def history(symbol: StockQuery, current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return ok(data=forecast_runs.history(db, current.id, symbol))


@router.post("/runs")
def run(payload: StartForecast, current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return ok(data=forecast_runs.start_manual(db, current.id, payload.symbol))


@router.post("/runs/{run_id}/retry")
def retry(run_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return ok(data=forecast_runs.retry(db, current.id, run_id))


@router.put("/tracking")
def tracking(payload: TrackForecast, current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return ok(data={"tracking": forecast_runs.set_tracking(db, current.id, payload.symbol, payload.enabled)})


@router.get("/replay")
def replay_report(symbol: StockQuery, current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return ok(data=forecast_replay.latest(db, current.id, symbol))


@router.post("/replay")
def replay(payload: ReplayForecast, current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return ok(data=forecast_replay.start(db, current.id, payload.symbol,
                                        payload.model_dump(mode="json", exclude={"symbol"})))

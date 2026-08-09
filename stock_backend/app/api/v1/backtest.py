"""回测 API（4.4）：发起回测（异步）/任务状态轮询/结果查询。

N 区与全景K线策略指标数据源。任务在 Celery backtest 队列异步执行，不阻塞主线程。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import ok
from app.models.user import User
from app.schemas.backtest import BacktestCreateIn, BacktestResultOut, BacktestTaskOut
from app.services import backtest_service

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])


@router.post("")
def create_backtest(
    payload: BacktestCreateIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    task = backtest_service.create_backtest(
        db,
        current.id,
        payload.strategy_id,
        payload.symbol,
        payload.period,
        payload.start,
        payload.end,
        payload.fill_on,
    )
    return ok(data=BacktestTaskOut.model_validate(task).model_dump(mode="json"), msg="回测已提交")


@router.get("/tasks")
def list_tasks(
    strategy_id: int | None = None,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = backtest_service.list_tasks(db, current.id, strategy_id)
    return ok(data=[BacktestTaskOut.model_validate(t).model_dump(mode="json") for t in rows])


@router.get("/tasks/{task_id}")
def get_task(
    task_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    task = backtest_service.get_task(db, current.id, task_id)
    return ok(data=BacktestTaskOut.model_validate(task).model_dump(mode="json"))


@router.get("/results")
def list_results(
    strategy_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = backtest_service.list_results(db, current.id, strategy_id)
    return ok(data=[BacktestResultOut.model_validate(r).model_dump(mode="json") for r in rows])


@router.get("/results/{result_id}")
def get_result(
    result_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    result = backtest_service.get_result(db, current.id, result_id)
    return ok(data=BacktestResultOut.model_validate(result).model_dump(mode="json"))

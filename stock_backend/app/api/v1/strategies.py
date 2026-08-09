"""交易策略 API：AI 生成（3.5）+ CRUD（3.6）。

注意：/strategies/generate 必须声明在 /strategies/{id} 之前，避免路径参数吞掉 action。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent import strategy_gen
from app.api.deps import get_current_user, get_db
from app.core.response import ok
from app.models.user import User
from app.schemas.strategy import (
    StrategyCreateIn,
    StrategyGenerateIn,
    StrategyOut,
    StrategyOutput,
    StrategyUpdateIn,
)
from app.services import strategy_service

router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])


@router.post("/generate")
async def generate_strategy(
    payload: StrategyGenerateIn,
    current: User = Depends(get_current_user),
) -> dict:
    out = await strategy_gen.generate_strategy(payload.description)
    return ok(data=StrategyOutput.model_validate(out).model_dump(mode="json"))


# ---- 3.6 CRUD ----
@router.get("")
def list_strategies(current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = strategy_service.list_strategies(db, current.id)
    return ok(data=[StrategyOut.model_validate(s).model_dump(mode="json") for s in rows])


@router.post("")
def create_strategy(
    payload: StrategyCreateIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = strategy_service.create_strategy(
        db, current.id, payload.title, payload.description, payload.code, payload.params, payload.status
    )
    return ok(data=StrategyOut.model_validate(row).model_dump(mode="json"), msg="保存成功")


@router.get("/{strategy_id}")
def get_strategy(
    strategy_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = strategy_service.get_strategy(db, current.id, strategy_id)
    return ok(data=StrategyOut.model_validate(row).model_dump(mode="json"))


@router.put("/{strategy_id}")
def update_strategy(
    strategy_id: int,
    payload: StrategyUpdateIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = strategy_service.update_strategy(
        db,
        current.id,
        strategy_id,
        payload.title,
        payload.description,
        payload.code,
        payload.params,
        payload.status,
    )
    return ok(data=StrategyOut.model_validate(row).model_dump(mode="json"), msg="更新成功")


@router.delete("/{strategy_id}")
def delete_strategy(
    strategy_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    strategy_service.delete_strategy(db, current.id, strategy_id)
    return ok(msg="删除成功")

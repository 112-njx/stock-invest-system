"""支撑/压力位 API：列表（可按标的过滤）/添加/删除（K 线图叠加横线数据源）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import ok
from app.models.user import User
from app.schemas.user import SupportResistanceIn, SupportResistanceOut
from app.services import user_service

router = APIRouter(prefix="/api/v1/support-resistance", tags=["support-resistance"])


@router.get("")
def list_support_resistance(
    symbol_id: int | None = Query(None, description="按标的过滤"),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = user_service.list_support_resistance(db, current.id, symbol_id)
    data = [SupportResistanceOut.model_validate(r).model_dump(mode="json") for r in rows]
    return ok(data=data)


@router.post("")
def add_support_resistance(
    payload: SupportResistanceIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = user_service.add_support_resistance(db, current.id, payload.symbol, payload.type, payload.price, payload.note)
    return ok(data=SupportResistanceOut.model_validate(row).model_dump(mode="json"), msg="添加成功")


@router.delete("/{sr_id}")
def delete_support_resistance(
    sr_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    user_service.delete_support_resistance(db, current.id, sr_id)
    return ok(msg="删除成功")

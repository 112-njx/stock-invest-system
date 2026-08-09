"""重点关注股票 API：列表（合并实时价）/添加（幂等）/删除。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import ok
from app.models.user import User
from app.schemas.user import WatchlistAddIn, WatchlistOut
from app.services import user_service

router = APIRouter(prefix="/api/v1/watchlist", tags=["watchlist"])


@router.get("")
def list_watchlist(current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = user_service.list_watchlist(db, current.id)
    return ok(data=rows)


@router.post("")
def add_watchlist(
    payload: WatchlistAddIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = user_service.add_watchlist(db, current.id, payload.symbol)
    return ok(data=WatchlistOut.model_validate(row).model_dump(mode="json"), msg="添加成功")


@router.delete("/{watchlist_id}")
def delete_watchlist(
    watchlist_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    user_service.delete_watchlist(db, current.id, watchlist_id)
    return ok(msg="删除成功")

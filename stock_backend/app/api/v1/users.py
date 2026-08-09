"""用户 API：当前用户信息查询/更新（昵称、头像）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import ok
from app.models.user import User
from app.schemas.user import UserOut, UserUpdateIn
from app.services import user_service

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me")
def get_me(current: User = Depends(get_current_user)) -> dict:
    return ok(data=UserOut.model_validate(current).model_dump(mode="json"))


@router.put("/me")
def update_me(
    payload: UserUpdateIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    user = user_service.update_profile(db, current, nickname=payload.nickname, avatar_url=payload.avatar_url)
    return ok(data=UserOut.model_validate(user).model_dump(mode="json"))

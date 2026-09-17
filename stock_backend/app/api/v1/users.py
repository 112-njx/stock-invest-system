"""用户 API：当前用户信息查询/更新（昵称、头像）+ 改密/改邮箱（G33）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import ok
from app.models.user import User
from app.schemas.user import ChangeEmailIn, ChangePasswordIn, UserOut, UserUpdateIn
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


@router.put("/me/password")
def change_password(
    payload: ChangePasswordIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """G33：修改密码（需旧密码校验），成功后吊销全部会话。"""
    user_service.change_password(db, current, payload.old_password, payload.new_password)
    return ok(data={"message": "密码修改成功，请重新登录"})


@router.put("/me/email")
def change_email(
    payload: ChangeEmailIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """G33：修改邮箱（需密码校验），新邮箱置未验证并发送验证邮件。"""
    result = user_service.change_email(db, current, payload.password, payload.new_email)
    return ok(data=result)

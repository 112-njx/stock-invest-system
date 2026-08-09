"""鉴权 API：注册、登录（签发 JWT）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.response import ok
from app.schemas.user import LoginIn, RegisterIn, TokenOut
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register")
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> dict:
    token = auth_service.register(db, payload)
    return ok(data=TokenOut.model_validate(token).model_dump(mode="json"))


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)) -> dict:
    token = auth_service.login(db, payload)
    return ok(data=TokenOut.model_validate(token).model_dump(mode="json"))

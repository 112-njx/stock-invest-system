"""鉴权服务：注册、登录（bcrypt 校验 → 签发 JWT）。"""

from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.core.security import create_access_token, hash_password, verify_password
from app.repositories import user_repo
from app.schemas.user import LoginIn, RegisterIn, TokenOut, UserOut


def register(db: Session, payload: RegisterIn) -> TokenOut:
    username = payload.username.strip()
    if user_repo.get_by_username(db, username):
        raise ApiError(status_code=400, code=40001, msg="用户名已被占用")
    user = user_repo.create(db, username, hash_password(payload.password), payload.email, payload.nickname)
    db.commit()
    db.refresh(user)
    return TokenOut(token=create_access_token(user.id), user=UserOut.model_validate(user))


def login(db: Session, payload: LoginIn) -> TokenOut:
    user = user_repo.get_by_username(db, payload.username.strip())
    if user is None or not verify_password(payload.password, user.password_hash):
        raise ApiError(status_code=401, code=40101, msg="用户名或密码错误")
    return TokenOut(token=create_access_token(user.id), user=UserOut.model_validate(user))

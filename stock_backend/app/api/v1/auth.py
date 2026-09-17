"""鉴权 API：注册、登录、刷新、登出、会话管理（G19 双 token）+ 邮箱验证/密码重置（G23）。"""

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.response import ok
from app.core.security import (
    clear_access_token_cookie,
    clear_refresh_token_cookie,
    hash_refresh_token,
    set_access_token_cookie,
    set_refresh_token_cookie,
)
from app.models.user import User
from app.schemas.user import ForgotPasswordIn, LoginIn, RegisterIn, ResetPasswordIn
from app.services import auth_service

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
_settings = get_settings()


def _get_client_info(request: Request) -> tuple[str | None, str | None]:
    """提取客户端 User-Agent 和 IP。"""
    user_agent = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    return user_agent, ip


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """种下双 token Cookie（G29：access Cookie 供 WS 握手鉴权，浏览器 WS 无法带 header）。"""
    set_access_token_cookie(
        response, access_token, max_age=_settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    set_refresh_token_cookie(
        response, refresh_token, max_age=_settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
    )


@router.post("/register")
def register(payload: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    ua, ip = _get_client_info(request)
    result = auth_service.register(db, payload, user_agent=ua, ip_address=ip)
    _set_auth_cookies(response, result["token"], result["refresh_token"])
    return ok(data={"token": result["token"], "user": result["user"]})


@router.post("/login")
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    ua, ip = _get_client_info(request)
    result = auth_service.login(db, payload, user_agent=ua, ip_address=ip)
    _set_auth_cookies(response, result["token"], result["refresh_token"])
    return ok(data={"token": result["token"], "user": result["user"]})


@router.post("/refresh")
def refresh_token(request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    """刷新 token：从 Cookie 读 refresh token → 轮换签发新双 token。"""
    old_refresh = request.cookies.get(_settings.REFRESH_TOKEN_COOKIE_NAME)
    if not old_refresh:
        clear_refresh_token_cookie(response)
        from app.core.exceptions import ApiError
        raise ApiError(status_code=401, code=40102, msg="刷新令牌缺失")

    ua, ip = _get_client_info(request)
    result = auth_service.refresh(db, old_refresh, user_agent=ua, ip_address=ip)

    # 轮换后同步刷新双 Cookie（access Cookie 供 WS 握手使用）
    _set_auth_cookies(response, result["token"], result["refresh_token"])
    return ok(data={"token": result["token"]})


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """登出：吊销 access + refresh + 清双 Cookie。"""
    # access token 优先取 header，回退 Cookie（G29：WS 场景只有 Cookie）
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header.replace("Bearer ", "")
    else:
        access_token = request.cookies.get(_settings.ACCESS_TOKEN_COOKIE_NAME, "")
    refresh_token = request.cookies.get(_settings.REFRESH_TOKEN_COOKIE_NAME)

    auth_service.logout(db, access_token, refresh_token)
    clear_access_token_cookie(response)
    clear_refresh_token_cookie(response)
    return ok(data=None)


@router.get("/sessions")
def list_sessions(
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """活跃设备列表（含当前设备标记）。"""
    current_refresh = request.cookies.get(_settings.REFRESH_TOKEN_COOKIE_NAME)
    current_hash = hash_refresh_token(current_refresh) if current_refresh else None
    sessions = auth_service.get_sessions(db, current.id, current_hash)
    return ok(data=sessions)


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """踢出指定设备。"""
    auth_service.revoke_session_by_id(db, current.id, session_id)
    return ok(data=None)


# ==================================================================
# G23：邮箱验证 / 密码重置
# ==================================================================


@router.get("/verify-email")
def verify_email(
    token: str = Query(..., description="验证 token（从邮件链接获取）"),
    db: Session = Depends(get_db),
) -> dict:
    """邮箱验证：校验 token → 标记 email_verified=True。"""
    result = auth_service.verify_email(db, token)
    return ok(data=result)


@router.post("/forgot-password")
def forgot_password(
    payload: ForgotPasswordIn,
    db: Session = Depends(get_db),
) -> dict:
    """忘记密码：按邮箱发送重置链接（无论邮箱是否存在均返回成功，防枚举）。"""
    result = auth_service.forgot_password(db, payload.email)
    return ok(data=result)


@router.post("/reset-password")
def reset_password(
    payload: ResetPasswordIn,
    db: Session = Depends(get_db),
) -> dict:
    """重置密码：校验 token → 更新密码 → 吊销所有会话。"""
    result = auth_service.reset_password(db, payload.token, payload.new_password)
    return ok(data=result)


# ==================================================================
# G18：账户恢复（宽限期内）
# ==================================================================


@router.post("/restore-account")
def restore_account(
    payload: LoginIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    """G18：宽限期内恢复已注销账户（用户名+密码校验），成功后签发新双 token。"""
    ua, ip = _get_client_info(request)
    result = auth_service.restore_account(
        db, payload.username, payload.password, user_agent=ua, ip_address=ip
    )
    _set_auth_cookies(response, result["token"], result["refresh_token"])
    return ok(data={"token": result["token"], "user": result["user"]}, msg="账户已恢复")

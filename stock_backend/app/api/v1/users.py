"""用户 API：当前用户信息查询/更新（昵称、头像）+ 改密/改邮箱（G33）+ 数据导出（G17）。"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.core.response import ok
from app.models.user import User
from app.repositories import export_repo, user_repo
from app.schemas.user import ApiKeyIn, ApiKeyOut, ChangeEmailIn, ChangePasswordIn, UserOut, UserUpdateIn
from app.services import export_token, user_service
from app.services.llm.user_key import ApiKeyFormatError, validate_api_key

_settings = get_settings()

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me")
def get_me(current: User = Depends(get_current_user)) -> dict:
    return ok(data=UserOut.from_user(current).model_dump(mode="json"))


@router.put("/me")
def update_me(
    payload: UserUpdateIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    user = user_service.update_profile(db, current, nickname=payload.nickname, avatar_url=payload.avatar_url)
    return ok(data=UserOut.from_user(user).model_dump(mode="json"))


@router.get("/me/api-key")
def get_api_key_status(current: User = Depends(get_current_user)) -> dict:
    """G14：查询自填 API Key 配置状态（只回掩码，不回明文）。"""
    key = current.api_key_encrypted
    masked = f"{key[:7]}****{key[-4:]}" if key and len(key) > 12 else ("已配置" if key else None)
    return ok(data=ApiKeyOut(has_api_key=bool(key), masked=masked).model_dump(mode="json"))


@router.put("/me/api-key")
def set_api_key(
    payload: ApiKeyIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """G14：设置/清除自填 API Key（加密存储）。

    传空串清除（回退服务端默认 key）；非空时做 sk- 前缀 + 形态校验。
    """
    raw = (payload.api_key or "").strip()
    if not raw:
        user_repo.set_api_key(db, current, None)
        db.commit()
        return ok(data=ApiKeyOut(has_api_key=False).model_dump(mode="json"), msg="已清除，将使用服务端默认 Key")

    try:
        key = validate_api_key(raw)
    except ApiKeyFormatError as e:
        raise ApiError(status_code=400, code=40030, msg=str(e)) from e

    user_repo.set_api_key(db, current, key)
    db.commit()
    masked = f"{key[:7]}****{key[-4:]}"
    return ok(data=ApiKeyOut(has_api_key=True, masked=masked).model_dump(mode="json"), msg="已保存")


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


# ==================================================================
# G17：用户数据导出（P1-5a 数据复制权）
# ==================================================================


def _export_out(row, download_token: str | None = None) -> dict:
    """导出任务响应体（含状态/进度/大小/过期时间；success 时附签名下载链接）。"""
    return {
        "task_id": row.id,
        "status": row.status,
        "progress": row.progress,
        "file_size": row.file_size,
        "error": row.error,
        "created_at": row.created_at,
        "finished_at": row.finished_at,
        "expires_at": row.expires_at,
        "download_url": (
            f"/api/v1/users/me/export/{row.id}/download?token={download_token}"
            if download_token
            else None
        ),
    }


@router.post("/me/export")
def create_export(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """G17：创建数据导出任务（异步 Celery），生成全量个人数据 ZIP。"""
    expires_at = datetime.now(UTC) + timedelta(hours=_settings.EXPORT_TTL_HOURS)
    row = export_repo.create(db, current.id, expires_at=expires_at)
    db.commit()
    db.refresh(row)

    from app.worker.tasks.export_tasks import run_user_export

    run_user_export.delay(task_id=row.id)  # 异步执行，不阻塞请求
    return ok(data=_export_out(row), msg="导出任务已提交")


@router.get("/me/export/{task_id}")
def get_export_status(
    task_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """G17：查询导出任务状态与进度；成功后返回带签名 token 的下载链接。"""
    row = export_repo.get_owned(db, current.id, task_id)
    if row is None:
        raise ApiError(status_code=404, code=40420, msg="导出任务不存在")
    token = export_token.create_download_token(current.id, row.id) if row.status == "success" else None
    return ok(data=_export_out(row, token))


@router.get("/me/export/{task_id}/download")
def download_export(
    task_id: int,
    token: str = Query(..., description="签名下载 token（从状态接口的 download_url 获取）"),
    db: Session = Depends(get_db),
) -> FileResponse:
    """G17：按签名 token 下载导出 ZIP（token 含 user_id + task_id，防越权）。"""
    parsed = export_token.verify_download_token(token)
    if parsed is None:
        raise ApiError(status_code=403, code=40301, msg="下载链接无效或已过期")
    user_id, token_task_id = parsed
    if token_task_id != task_id:
        raise ApiError(status_code=403, code=40301, msg="下载链接无效或已过期")

    row = export_repo.get_owned(db, user_id, task_id)
    if row is None:
        raise ApiError(status_code=404, code=40420, msg="导出任务不存在")
    if row.status != "success" or not row.file_path:
        raise ApiError(status_code=400, code=40030, msg="导出文件不可用（未完成或已过期）")

    path = Path(row.file_path)
    if not path.exists():
        raise ApiError(status_code=404, code=40421, msg="导出文件已过期或被清理")
    return FileResponse(
        path,
        media_type="application/zip",
        filename=path.name,
    )


# ==================================================================
# G18：账户删除（P1-5b 删除权）
# ==================================================================


@router.delete("/me")
def delete_me(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """G18：注销账户（软删除）。

    置 is_deleted/deleted_at + 立即吊销全部 refresh session；access token 因
    get_current_user 的 is_deleted 检查即刻失效。30 天宽限期内可经
    POST /api/v1/auth/restore-account 恢复，逾期由 beat 硬删级联清理全部数据。
    """
    result = user_service.delete_account(db, current)
    return ok(data=result, msg="账户已注销")

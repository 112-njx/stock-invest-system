"""记忆管理 API（阶段六 6.4 + G15 审计）：M 区「记忆文件」查看/删除/清空 + 访问审计。

- GET    /api/v1/memory/facts         分页返回用户记忆（内容摘要、重要性、来源对话ID、创建时间），支持按重要性筛选
- DELETE /api/v1/memory/facts/{id}    删除单条记忆（删 memory_chunks 行，向量同列同删）
- DELETE /api/v1/memory/facts         清空全部记忆（按 user_id 删 memory_chunks 行）
- GET    /api/v1/memory/audit         G15：分页返回记忆访问审计日志（读取/写入/删除）
"""

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.agent.memory import memory_service
from app.api.deps import get_current_user, get_db
from app.core.exceptions import ApiError
from app.core.response import ok
from app.models.user import User
from app.repositories import audit_repo
from app.schemas.agent import AuditLogOut, MemoryFactOut

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


def client_ip(request: Request) -> str | None:
    """取请求来源 IP（优先 X-Forwarded-For 首段，适配 Nginx 反代）。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.client.host if request.client else None


@router.get("/facts")
def list_facts(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
    importance_min: int | None = Query(None, ge=1, le=10, description="重要性下限筛选"),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows, total = memory_service.list_facts(db, current.id, importance_min=importance_min, page=page, size=size)
    return ok(data={"items": [MemoryFactOut.model_validate(r).model_dump(mode="json") for r in rows], "total": total, "page": page, "size": size})


@router.get("/audit")
def list_audit_logs(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
    action: str | None = Query(None, description="按动作筛选：memory_read / memory_write / memory_delete"),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """G15：记忆访问审计（读取/写入/删除），按时间倒序。"""
    offset = (page - 1) * size
    rows = audit_repo.list_logs(db, current.id, action=action, offset=offset, limit=size)
    total = audit_repo.count_logs(db, current.id, action=action)
    return ok(data={"items": [AuditLogOut.model_validate(r).model_dump(mode="json") for r in rows], "total": total, "page": page, "size": size})


@router.delete("/facts/{fact_id}")
def delete_fact(
    fact_id: int,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not memory_service.delete_fact(db, current.id, fact_id, ip=client_ip(request)):
        raise ApiError(status_code=404, code=40450, msg="记忆不存在")
    return ok(msg="已删除")


@router.delete("/facts")
def clear_facts(
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    deleted = memory_service.clear_all_facts(db, current.id, ip=client_ip(request))
    return ok(data={"deleted": deleted}, msg="已清空")

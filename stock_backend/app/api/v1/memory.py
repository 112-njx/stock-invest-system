"""记忆管理 API（阶段六 6.4）：M 区「记忆文件」查看/删除/清空。

- GET    /api/v1/memory/facts         分页返回用户记忆（内容摘要、重要性、来源对话ID、创建时间），支持按重要性筛选
- DELETE /api/v1/memory/facts/{id}    删除单条记忆（同步删 ChromaDB 向量 + PG 记录）
- DELETE /api/v1/memory/facts         清空全部记忆（重建 ChromaDB collection）
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.agent.memory import memory_service
from app.api.deps import get_current_user, get_db
from app.core.exceptions import ApiError
from app.core.response import ok
from app.models.user import User
from app.schemas.agent import MemoryFactOut

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


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


@router.delete("/facts/{fact_id}")
def delete_fact(
    fact_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not memory_service.delete_fact(db, current.id, fact_id):
        raise ApiError(status_code=404, code=40450, msg="记忆不存在")
    return ok(msg="已删除")


@router.delete("/facts")
def clear_facts(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    deleted = memory_service.clear_all_facts(db, current.id)
    return ok(data={"deleted": deleted}, msg="已清空")

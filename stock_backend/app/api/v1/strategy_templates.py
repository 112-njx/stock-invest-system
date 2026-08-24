"""策略模板 API（阶段八 8.5）：内置策略模板列表/详情，供「基于模板创建」。

- GET /api/v1/strategy-templates      模板列表（id/name/description/params_schema，不含完整 code）
- GET /api/v1/strategy-templates/{id} 单模板详情（含完整 code）
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import ok
from app.models.user import User
from app.schemas.strategy import StrategyTemplateListItem, StrategyTemplateOut
from app.services import strategy_service

router = APIRouter(prefix="/api/v1/strategy-templates", tags=["strategy-templates"])


@router.get("")
def list_templates(current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = strategy_service.list_templates(db)
    return ok(data=[StrategyTemplateListItem.model_validate(r).model_dump(mode="json") for r in rows])


@router.get("/{template_id}")
def get_template(
    template_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = strategy_service.get_template(db, template_id)
    return ok(data=StrategyTemplateOut.model_validate(row).model_dump(mode="json"))

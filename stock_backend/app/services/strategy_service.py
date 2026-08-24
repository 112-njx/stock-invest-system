"""交易策略服务：保存/列表/详情/更新/删除，按 user 隔离。"""

from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.models.strategy import StrategyTemplate, TradingStrategy
from app.repositories import strategy_repo


# ---- 策略模板（阶段八 8.5：全局模板，无 user 隔离）----
def list_templates(db: Session) -> list[StrategyTemplate]:
    return strategy_repo.list_templates(db)


def get_template(db: Session, template_id: int) -> StrategyTemplate:
    row = strategy_repo.get_template(db, template_id)
    if row is None:
        raise ApiError(status_code=404, code=40421, msg="策略模板不存在")
    return row


def create_strategy(db: Session, user_id: int, title: str, description: str | None, code: str | None, params: dict | None, status: str) -> TradingStrategy:
    row = strategy_repo.create_strategy(db, user_id, title, description, code, params, status)
    db.commit()
    db.refresh(row)
    return row


def list_strategies(db: Session, user_id: int) -> list[TradingStrategy]:
    return strategy_repo.list_strategies(db, user_id)


def _get_owned(db: Session, user_id: int, strategy_id: int) -> TradingStrategy:
    row = strategy_repo.get_strategy(db, user_id, strategy_id)
    if row is None:
        raise ApiError(status_code=404, code=40420, msg="策略不存在")
    return row


def get_strategy(db: Session, user_id: int, strategy_id: int) -> TradingStrategy:
    return _get_owned(db, user_id, strategy_id)


def update_strategy(
    db: Session,
    user_id: int,
    strategy_id: int,
    title: str | None,
    description: str | None,
    code: str | None,
    params: dict | None,
    status: str | None,
) -> TradingStrategy:
    row = _get_owned(db, user_id, strategy_id)
    fields = {"title": title, "description": description, "code": code, "params": params, "status": status}
    row = strategy_repo.update_strategy(db, row, **{k: v for k, v in fields.items() if v is not None})
    db.commit()
    db.refresh(row)
    return row


def delete_strategy(db: Session, user_id: int, strategy_id: int) -> None:
    if not strategy_repo.delete_strategy(db, user_id, strategy_id):
        raise ApiError(status_code=404, code=40420, msg="策略不存在")
    db.commit()

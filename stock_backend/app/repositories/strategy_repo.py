"""交易策略读写（trading_strategies），按 user 隔离（借鉴 QuantDinger 多租户）。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.strategy import StrategyTemplate, TradingStrategy


# ---- strategy_templates（阶段八 8.5）----
def list_templates(db: Session) -> list[StrategyTemplate]:
    return list(db.scalars(select(StrategyTemplate).order_by(StrategyTemplate.sort_order, StrategyTemplate.id)))


def get_template(db: Session, template_id: int) -> StrategyTemplate | None:
    return db.get(StrategyTemplate, template_id)


def create_strategy(
    db: Session,
    user_id: int,
    title: str,
    description: str | None,
    code: str | None,
    params: dict | None,
    status: str,
) -> TradingStrategy:
    row = TradingStrategy(user_id=user_id, title=title, description=description, code=code, params=params, status=status)
    db.add(row)
    db.flush()
    return row


def list_strategies(db: Session, user_id: int) -> list[TradingStrategy]:
    return list(db.scalars(select(TradingStrategy).where(TradingStrategy.user_id == user_id).order_by(TradingStrategy.id.desc())))


def get_strategy(db: Session, user_id: int, strategy_id: int) -> TradingStrategy | None:
    return db.scalar(
        select(TradingStrategy).where(TradingStrategy.id == strategy_id, TradingStrategy.user_id == user_id)
    )


def update_strategy(db: Session, row: TradingStrategy, **fields) -> TradingStrategy:
    for k, v in fields.items():
        if v is not None:
            setattr(row, k, v)
    db.flush()
    return row


def delete_strategy(db: Session, user_id: int, strategy_id: int) -> bool:
    row = get_strategy(db, user_id, strategy_id)
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True

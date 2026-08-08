"""K 线按月分区管理：建分区、越界写兜底（默认分区已由迁移建好）。"""

from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.kline import KLINE_MODELS

# 四个 K 线父表名（与迁移 create_kline_partitions 对应）
KLINE_TABLES = tuple(model.__tablename__ for model in KLINE_MODELS.values())


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    return date(d.year + m // 12, m % 12 + 1, 1)


def create_kline_partitions(db: Session, table_name: str, start: date, end: date) -> None:
    """调用 DB 函数按月批量建分区（幂等：IF NOT EXISTS）。"""
    db.execute(
        text("SELECT create_kline_partitions(:t, :s, :e)"),
        {"t": table_name, "s": start, "e": end},
    )


def ensure_current_partitions(db: Session, extend_months: int = 2) -> None:
    """确保四个 K 线父表覆盖「当前月 + 未来 extend_months 月」分区。

    越界写由迁移创建的 *_default 兜底分区承接，不会报错；此函数用于按月提前扩容。
    """
    start = datetime.now().date().replace(day=1)
    end = _add_months(start, extend_months)
    for t in KLINE_TABLES:
        create_kline_partitions(db, t, start, end)

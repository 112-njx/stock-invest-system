"""标的查询/写入（symbols 表）。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.symbol import Symbol


def get_by_id(db: Session, symbol_id: int) -> Symbol | None:
    return db.get(Symbol, symbol_id)


def get_by_code(db: Session, code: str) -> Symbol | None:
    return db.scalar(select(Symbol).where(Symbol.code == code))


def get_by_name(db: Session, name: str, type_: str | None = None) -> Symbol | None:
    stmt = select(Symbol).where(Symbol.name == name)
    if type_:
        stmt = stmt.where(Symbol.type == type_)
    return db.scalar(stmt)


def list_symbols(
    db: Session,
    type_: str | None = None,
    search: str | None = None,
    fixed_only: bool | None = None,
) -> list[Symbol]:
    stmt = select(Symbol)
    if type_:
        stmt = stmt.where(Symbol.type == type_)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(Symbol.code.like(like) | Symbol.name.like(like))
    if fixed_only is not None:
        stmt = stmt.where(Symbol.is_fixed_index.is_(fixed_only))
    stmt = stmt.order_by(Symbol.sort_order.nullslast(), Symbol.id)
    return list(db.scalars(stmt))


def list_kline_sync_symbols(db: Session) -> list[Symbol]:
    """行情同步候选：有 code 的股票/ETF/指数 + 固定行业指数（code 空，按名称拉取）。"""
    return list(
        db.scalars(
            select(Symbol)
            .where(
                (Symbol.type.in_(("stock", "etf", "index"))) & ((Symbol.code != "") | Symbol.is_fixed_index.is_(True))
            )
            .order_by(Symbol.id)
        )
    )


def list_fixed_indices(db: Session) -> list[Symbol]:
    """固定大盘/行业指数（is_fixed_index=True，按 sort_order 排序），G/H 区数据源。"""
    return list(
        db.scalars(
            select(Symbol).where(Symbol.is_fixed_index.is_(True)).order_by(Symbol.sort_order.nullslast(), Symbol.id)
        )
    )


def list_realtime_symbols(db: Session) -> list[Symbol]:
    """实时轮询候选：固定大盘/行业指数 + 已入库的其他标的。"""
    return list(
        db.scalars(
            select(Symbol)
            .where(Symbol.is_fixed_index.is_(True) | (Symbol.type.in_(("stock", "etf"))))
            .order_by(Symbol.id)
        )
    )


def update_code(db: Session, symbol_id: int, code: str) -> None:
    """回填行业指数 code（幂等）。"""
    sym = db.get(Symbol, symbol_id)
    if sym and sym.code != code:
        sym.code = code
        db.flush()


# ---- 全量目录（V0.2 阶段三）----
def upsert_catalog_symbols(db: Session, items: list[tuple[str, str, str, str]]) -> int:
    """目录标的幂等 upsert：新标的 is_catalog=True，已存在保留原状态（已同步K线的不降级）。返回新增数。

    三层防撞唯一约束 uq_symbols_type_name：
    1) 查重按 (type, name) 对齐约束（全市场 ETF 存在同名不同 code 的标的，按 code 查重会全量新增撞约束）；
    2) seen 集合防同批内同名重复（同批多次出现 (type,name) 时查询不可见已 add 的 pending 行）；
    3) 每 100 条 flush 一次使 pending 行对后续查询可见（Session autoflush=False，不 flush 则查询看不到已 add 行）。
    """
    added = 0
    seen: set[tuple[str, str]] = set()
    for i, (code, name, type_, market) in enumerate(items, 1):
        if not code:
            continue
        key = (type_, name)
        if key in seen:
            continue
        existing = db.scalar(select(Symbol).where(Symbol.type == type_, Symbol.name == name))
        if existing:
            if not existing.name:
                existing.name = name
            seen.add(key)
            continue
        db.add(Symbol(code=code, name=name, type=type_, market=market or "SSE", is_catalog=True))
        seen.add(key)
        added += 1
        if added % 100 == 0:
            db.flush()
    db.flush()
    return added


def count_catalog_stocks(db: Session) -> int:
    """目录内 A 股数量（is_catalog=True AND type='stock'），用于启动检查阈值。"""
    return db.scalar(select(func.count(Symbol.id)).where(Symbol.is_catalog.is_(True), Symbol.type == "stock")) or 0


def count_type(db: Session, type_: str) -> int:
    """某类型标的总数（目录同步后校验数量用）。"""
    return db.scalar(select(func.count(Symbol.id)).where(Symbol.type == type_)) or 0

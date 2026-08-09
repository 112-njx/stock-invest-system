"""用户域服务：资料更新、重点关注股票（合并实时价）、支撑/压力位。"""

from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.models.symbol import Symbol
from app.models.user import User, UserWatchlist
from app.repositories import symbol_repo, user_repo
from app.schemas.user import WatchlistOut
from app.services import market_service


def update_profile(db: Session, user: User, nickname: str | None = None, avatar_url: str | None = None) -> User:
    user = user_repo.update_profile(db, user, nickname=nickname, avatar_url=avatar_url)
    db.commit()
    db.refresh(user)
    return user


def _resolve_symbol_id(db: Session, symbol: str) -> int:
    """解析标的（代码或 id），不存在抛 400。"""
    sym = symbol_repo.get_by_code(db, symbol)
    if sym:
        return sym.id
    if symbol.isdigit():
        sym = db.get(Symbol, int(symbol))
        if sym:
            return sym.id
    raise ApiError(status_code=400, code=40002, msg=f"标的不存在: {symbol}")


# ---- 重点关注股票 ----
def _watchlist_row(db: Session, entry: UserWatchlist) -> dict:
    """合并实时快照构造关注列表行（代码/名称/最新价/涨跌幅）。"""
    snaps = market_service.get_snapshots(db, [entry.symbol_id])
    snap = snaps[0] if snaps else {}
    return WatchlistOut(
        id=entry.id,
        symbol_id=entry.symbol_id,
        code=snap.get("code", ""),
        name=snap.get("name", ""),
        type=snap.get("type", ""),
        price=snap.get("price"),
        change=snap.get("change"),
        change_pct=snap.get("change_pct"),
        updated_at=snap.get("updated_at"),
        created_at=entry.created_at,
    ).model_dump(mode="json")


def add_watchlist(db: Session, user_id: int, symbol: str) -> dict:
    symbol_id = _resolve_symbol_id(db, symbol)
    entry = user_repo.add_watchlist(db, user_id, symbol_id)
    db.commit()
    db.refresh(entry)
    return _watchlist_row(db, entry)


def list_watchlist(db: Session, user_id: int) -> list[dict]:
    entries = user_repo.list_watchlist(db, user_id)
    return [_watchlist_row(db, e) for e in entries]


def delete_watchlist(db: Session, user_id: int, watchlist_id: int) -> None:
    if not user_repo.delete_watchlist(db, user_id, watchlist_id):
        raise ApiError(status_code=404, code=40401, msg="关注记录不存在")
    db.commit()


# ---- 支撑/压力位 ----
def add_support_resistance(db: Session, user_id: int, symbol: str, type_: str, price: float, note: str | None):
    symbol_id = _resolve_symbol_id(db, symbol)
    row = user_repo.add_support_resistance(db, user_id, symbol_id, type_, price, note)
    db.commit()
    db.refresh(row)
    return row


def list_support_resistance(db: Session, user_id: int, symbol_id: int | None = None) -> list:
    return user_repo.list_support_resistance(db, user_id, symbol_id)


def delete_support_resistance(db: Session, user_id: int, sr_id: int) -> None:
    if not user_repo.delete_support_resistance(db, user_id, sr_id):
        raise ApiError(status_code=404, code=40402, msg="支撑/压力位记录不存在")
    db.commit()

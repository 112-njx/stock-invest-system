"""用户域读写：users / user_watchlist / support_resistance。

多租户隔离（借鉴 QuantDinger）：所有业务查询强制带 user_id 过滤，防止越权。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import SupportResistance, User, UserWatchlist


# ---- users ----
def get_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def create(db: Session, username: str, password_hash: str, email: str | None, nickname: str | None) -> User:
    user = User(username=username, password_hash=password_hash, email=email, nickname=nickname)
    db.add(user)
    db.flush()
    return user


def update_profile(db: Session, user: User, nickname: str | None = None, avatar_url: str | None = None) -> User:
    if nickname is not None:
        user.nickname = nickname
    if avatar_url is not None:
        user.avatar_url = avatar_url
    db.flush()
    return user


# ---- user_watchlist ----
def list_watchlist(db: Session, user_id: int) -> list[UserWatchlist]:
    return list(
        db.scalars(select(UserWatchlist).where(UserWatchlist.user_id == user_id).order_by(UserWatchlist.id.desc()))
    )


def get_watchlist_entry(db: Session, user_id: int, symbol_id: int) -> UserWatchlist | None:
    return db.scalar(
        select(UserWatchlist).where(UserWatchlist.user_id == user_id, UserWatchlist.symbol_id == symbol_id)
    )


def add_watchlist(db: Session, user_id: int, symbol_id: int) -> UserWatchlist:
    """幂等添加：UNIQUE(user_id, symbol_id)，重复添加直接返回已存在记录。"""
    row = get_watchlist_entry(db, user_id, symbol_id)
    if row:
        return row
    row = UserWatchlist(user_id=user_id, symbol_id=symbol_id)
    db.add(row)
    db.flush()
    return row


def delete_watchlist(db: Session, user_id: int, watchlist_id: int) -> bool:
    row = db.scalar(select(UserWatchlist).where(UserWatchlist.id == watchlist_id, UserWatchlist.user_id == user_id))
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


# ---- support_resistance ----
def list_support_resistance(db: Session, user_id: int, symbol_id: int | None = None) -> list[SupportResistance]:
    stmt = select(SupportResistance).where(SupportResistance.user_id == user_id)
    if symbol_id is not None:
        stmt = stmt.where(SupportResistance.symbol_id == symbol_id)
    return list(db.scalars(stmt.order_by(SupportResistance.created_at)))


def add_support_resistance(
    db: Session, user_id: int, symbol_id: int, type_: str, price, note: str | None
) -> SupportResistance:
    row = SupportResistance(user_id=user_id, symbol_id=symbol_id, type=type_, price=price, note=note)
    db.add(row)
    db.flush()
    return row


def delete_support_resistance(db: Session, user_id: int, sr_id: int) -> bool:
    row = db.scalar(
        select(SupportResistance).where(SupportResistance.id == sr_id, SupportResistance.user_id == user_id)
    )
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True

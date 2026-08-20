"""用户域服务：资料更新、重点关注股票（合并实时价 + 自动同步 + Redis 缓存）、支撑/压力位。"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.models.symbol import Symbol
from app.models.user import User, UserWatchlist
from app.repositories import symbol_repo, user_repo
from app.schemas.user import WatchlistOut
from app.services import market_service
from app.utils import market_cache


def update_profile(db: Session, user: User, nickname: str | None = None, avatar_url: str | None = None) -> User:
    user = user_repo.update_profile(db, user, nickname=nickname, avatar_url=avatar_url)
    db.commit()
    db.refresh(user)
    return user


def ensure_admins(db: Session) -> None:
    """按 ADMIN_USERNAMES 配置将指定用户置为管理员（启动时幂等调用，best-effort）。"""
    from app.core.config import get_settings

    usernames = [u.strip() for u in get_settings().ADMIN_USERNAMES.split(",") if u.strip()]
    if not usernames:
        return
    for name in usernames:
        user_repo.set_admin_by_username(db, name)
    db.commit()


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
def _watchlist_rows(db: Session, entries: list[UserWatchlist]) -> list[dict]:
    """批量合并实时快照构造关注列表行（一次查快照，避免 N+1）。"""
    symbol_ids = [e.symbol_id for e in entries]
    snaps = {s["symbol_id"]: s for s in market_service.get_snapshots(db, symbol_ids)} if symbol_ids else {}
    rows: list[dict] = []
    for e in entries:
        snap = snaps.get(e.symbol_id, {})
        rows.append(
            WatchlistOut(
                id=e.id,
                symbol_id=e.symbol_id,
                code=snap.get("code", ""),
                name=snap.get("name", ""),
                type=snap.get("type", ""),
                price=snap.get("price"),
                change=snap.get("change"),
                change_pct=snap.get("change_pct"),
                updated_at=snap.get("updated_at"),
                sync_status=e.sync_status,
                last_synced_at=e.last_synced_at,
                created_at=e.created_at,
            ).model_dump(mode="json")
        )
    return rows


def add_watchlist(db: Session, user_id: int, symbol: str) -> dict:
    """添加关注：校验标的存在 → 幂等写入 → 无K线标的异步触发 kline_init → 立即返回。"""
    symbol_id = _resolve_symbol_id(db, symbol)
    existing = user_repo.get_watchlist_entry(db, user_id, symbol_id)
    entry = user_repo.add_watchlist(db, user_id, symbol_id)
    if existing is None:  # 新增记录才触发/标记同步
        if market_service.has_kline(db, symbol_id):
            entry.sync_status = "done"
            entry.last_synced_at = datetime.now(UTC)
        else:
            entry.sync_status = "pending"
            from app.worker.tasks.sync_tasks import kline_init

            kline_init.delay(symbol_id=symbol_id)  # 异步同步该标的K线（不阻塞响应）
    db.commit()
    db.refresh(entry)
    result = _watchlist_rows(db, [entry])[0]
    market_cache.invalidate_watchlist_cache(user_id)
    return result


def list_watchlist(db: Session, user_id: int) -> list[dict]:
    """关注列表：Redis watchlist:{user_id} → PostgreSQL → 回写（TTL 300）。"""
    cached = market_cache.get_watchlist_cache(user_id)
    if cached is not None:
        return cached
    entries = user_repo.list_watchlist(db, user_id)
    rows = _watchlist_rows(db, entries)
    market_cache.set_watchlist_cache(user_id, rows)
    return rows


def delete_watchlist(db: Session, user_id: int, watchlist_id: int) -> None:
    if not user_repo.delete_watchlist(db, user_id, watchlist_id):
        raise ApiError(status_code=404, code=40401, msg="关注记录不存在")
    db.commit()
    market_cache.invalidate_watchlist_cache(user_id)


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

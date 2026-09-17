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


def change_password(db: Session, user: User, old_password: str, new_password: str) -> None:
    """G33：修改密码（校验旧密码）→ 吊销该用户全部 refresh token，强制所有设备重新登录。"""
    from app.core.security import hash_password, verify_password
    from app.services import session_service

    if not verify_password(old_password, user.password_hash):
        raise ApiError(status_code=400, code=40003, msg="当前密码不正确")
    if old_password == new_password:
        raise ApiError(status_code=400, code=40004, msg="新密码不能与当前密码相同")
    user_repo.update_password(db, user, hash_password(new_password))
    session_service.revoke_all_user_sessions(db, user.id)
    db.commit()


def change_email(db: Session, user: User, password: str, new_email: str) -> dict:
    """G33：修改邮箱（校验密码）→ 新邮箱置未验证并发送验证邮件。

    邮箱唯一性：已被他人占用则拒绝。
    """
    from app.core.security import verify_password
    from app.services import email_token

    if not verify_password(password, user.password_hash):
        raise ApiError(status_code=400, code=40003, msg="当前密码不正确")
    new_email = new_email.strip()
    if new_email == user.email:
        raise ApiError(status_code=400, code=40005, msg="新邮箱与当前邮箱相同")
    existing = user_repo.get_by_email(db, new_email)
    if existing is not None and existing.id != user.id:
        raise ApiError(status_code=400, code=40002, msg="该邮箱已被注册")

    user.email = new_email
    user.email_verified = False  # 新邮箱需重新验证
    db.flush()
    db.commit()

    # 发送验证邮件（best-effort，失败不阻断改邮箱）
    try:
        from app.core.config import get_settings
        from app.services.email_service import send_email

        token = email_token.create_verify_token(user.id, new_email)
        origins = get_settings().CORS_ORIGINS
        frontend_url = origins.split(",")[0].strip() if origins else "http://localhost:5173"
        verify_url = f"{frontend_url}/verify-email?token={token}"
        send_email(
            db=db,
            recipient=new_email,
            template_name="verify_email",
            context={"username": user.username, "verify_url": verify_url},
        )
    except Exception:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning("send verify email failed for %s (best-effort)", new_email, exc_info=True)
    return {"message": "邮箱已更新，请查收验证邮件完成验证"}


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

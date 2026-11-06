"""Shared, fail-closed market source switches; never cached in worker singletons."""
from sqlalchemy import text
from app.utils.db import get_session


def read() -> dict:
    with get_session() as db:
        row = db.execute(text("SELECT akshare_enabled, history_storage_enabled, auto_sync_enabled, revision FROM market_source_policy WHERE id=1")).mappings().one()
        return dict(row)


def akshare_enabled() -> bool:
    return bool(read()["akshare_enabled"])


def history_storage_enabled() -> bool:
    return bool(read()['history_storage_enabled'])


def invalidate_caches() -> None:
    """Refresh source namespaces without overwriting concurrently edited switches."""
    with get_session() as db:
        db.execute(text('UPDATE market_source_policy SET revision=revision+1 WHERE id=1'))
        db.commit()


def save(akshare: bool, history_storage: bool = False, auto_sync: bool = False) -> dict:
    with get_session() as db:
        db.execute(text("UPDATE market_source_policy SET akshare_enabled=:a, history_storage_enabled=:h, auto_sync_enabled=:u, revision=revision+1 WHERE id=1"),
                   {"a": akshare, "h": history_storage, "u": auto_sync})
        db.commit()
    return read()

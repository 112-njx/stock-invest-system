"""Shared, fail-closed market source switches; never cached in worker singletons."""
from sqlalchemy import text
from app.utils.db import get_session


def read() -> dict:
    with get_session() as db:
        row = db.execute(text("SELECT akshare_enabled, auto_update_enabled, revision FROM market_source_policy WHERE id=1")).mappings().one()
        return dict(row)


def akshare_enabled() -> bool:
    return bool(read()["akshare_enabled"])


def save(akshare: bool, auto_update: bool = False) -> dict:
    with get_session() as db:
        db.execute(text("UPDATE market_source_policy SET akshare_enabled=:a, auto_update_enabled=:u, revision=revision+1 WHERE id=1"),
                   {"a": akshare, "u": auto_update})
        db.commit()
    return read()

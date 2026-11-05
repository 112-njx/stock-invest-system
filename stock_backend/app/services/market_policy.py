"""Shared, fail-closed market source switches; never cached in worker singletons."""
from sqlalchemy import text
from app.utils.db import get_session


def read() -> dict:
    with get_session() as db:
        row = db.execute(text("SELECT akshare_enabled, snapshots_enabled, revision FROM market_source_policy WHERE id=1")).mappings().one()
        return dict(row)


def akshare_enabled() -> bool:
    return bool(read()["akshare_enabled"])


def snapshots_enabled() -> bool:
    policy = read()
    return bool(policy["akshare_enabled"] and policy["snapshots_enabled"])


def save(akshare: bool, snapshots: bool) -> dict:
    if snapshots and not akshare:
        raise ValueError("启用实时快照前，请先启用 AkShare 兜底")
    with get_session() as db:
        db.execute(text("UPDATE market_source_policy SET akshare_enabled=:a, snapshots_enabled=:s, revision=revision+1 WHERE id=1"),
                   {"a": akshare, "s": snapshots})
        db.commit()
    return read()

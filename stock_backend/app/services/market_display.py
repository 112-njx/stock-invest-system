"""Rendering preferences only: never used for source bars or indicators."""
from sqlalchemy import text
from app.utils.db import get_session


def read():
    with get_session() as db:
        return dict(db.execute(text('SELECT synthetic_wick_factor FROM market_source_policy WHERE id=1')).mappings().one())


def save(factor: float):
    with get_session() as db:
        db.execute(text('UPDATE market_source_policy SET synthetic_wick_factor=:factor WHERE id=1'), {'factor': factor})
        db.commit()
    return read()

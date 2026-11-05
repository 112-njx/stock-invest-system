"""Exercise the first-stock insert race against the project's local PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from app.models.symbol import Symbol
from app.services import stock_search_directory, user_service
from app.utils.db import get_session
from sqlalchemy import delete, select


def test_two_users_resolve_same_new_stock_atomically(monkeypatch):
    suffix = uuid4().hex[:10]
    code = f"tss{suffix}"
    item = {"code": code, "name": f"search_race_{suffix}", "market": "SZSE"}
    monkeypatch.setattr(stock_search_directory, "get_directory", lambda: {"items": [item]})
    barrier = Barrier(2)

    class RacingSession:
        def __init__(self, session):
            self.session = session
            self.first_lookup = True

        def scalar(self, statement):
            value = self.session.scalar(statement)
            if self.first_lookup:
                self.first_lookup = False
                assert value is None
                barrier.wait(timeout=10)
            return value

        def __getattr__(self, name):
            return getattr(self.session, name)

    def resolve():
        with get_session() as session:
            symbol_id = user_service._resolve_symbol_id(RacingSession(session), f"stock:{code}")
            session.commit()
            return symbol_id

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(resolve) for _ in range(2)]
            ids = [future.result(timeout=20) for future in futures]
        assert ids[0] == ids[1]
        with get_session() as session:
            assert list(session.scalars(select(Symbol.id).where(Symbol.code == code))) == [ids[0]]
    finally:
        with get_session() as session:
            session.execute(delete(Symbol).where(Symbol.code == code))
            session.commit()

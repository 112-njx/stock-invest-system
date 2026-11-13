"""Latest indicator queries must preserve warmup even beyond 100,000 bars."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.kline import Kline15m
from app.repositories import kline_repo
from app.services import indicator_policy, indicator_service, sdk_indicators, source_history


@pytest.fixture(scope='module')
def history():
    engine = create_engine('sqlite://')
    Kline15m.__table__.create(engine)
    first = datetime(1999, 1, 1, tzinfo=UTC)
    with Session(engine) as db:
        for offset in range(0, 100005, 5000):
            db.execute(Kline15m.__table__.insert(), [dict(
                symbol_id=999, ts=first + timedelta(minutes=15*i), source='stockdb',
                open=10, high=12, low=9, close=11, volume=i, amount=1000,
            ) for i in range(offset, min(offset + 5000, 100005))])
        db.commit()
        yield db, first
    engine.dispose()


@pytest.mark.parametrize('pandas_enabled', [False, True])
@pytest.mark.parametrize('transient', [False, True])
def test_default_indicators_include_newest_bars(monkeypatch, history, pandas_enabled, transient):
    db, first = history
    monkeypatch.setattr(kline_repo, 'use_transient_source', lambda *a: transient)
    monkeypatch.setattr(kline_repo, 'source_filter', lambda model, *a: model.source == 'stockdb')
    if transient:
        cached = list(db.scalars(select(Kline15m).order_by(Kline15m.ts)))
        monkeypatch.setattr(source_history, 'cached', lambda *a: cached)
    monkeypatch.setattr(indicator_service.market_service, 'resolve_symbol_id', lambda *a: 999)
    monkeypatch.setattr(indicator_policy, 'read', lambda: dict(pandas_enabled=pandas_enabled, revision=1))
    monkeypatch.setattr(indicator_service, '_cache_key', lambda *a, **kw: 'isolated-long-history')
    monkeypatch.setattr(indicator_service, '_get_cache', lambda *a: None)
    monkeypatch.setattr(indicator_service, '_set_cache', lambda *a: None)

    def sdk(rows, *args):
        assert len(rows) == 100005
        assert rows[0]['volume'] == 0
        assert rows[-1]['volume'] == 100004
        return rows

    monkeypatch.setattr(sdk_indicators, 'calculate', sdk)
    result = indicator_service.compute_indicators(db, '999', '15m', ['volume'], limit=5)
    assert [row['volume'] for row in result] == list(range(100000, 100005))
    assert datetime.fromisoformat(result[-1]['ts']).replace(tzinfo=UTC) == first + timedelta(minutes=15*100004)
    if pandas_enabled:
        assert result[-1]['volume_ma10'] == 99999.5


@pytest.mark.parametrize('transient', [False, True])
def test_latest_repository_query_respects_end_offset_and_order(monkeypatch, history, transient):
    db, first = history
    monkeypatch.setattr(kline_repo, 'use_transient_source', lambda *a: transient)
    monkeypatch.setattr(kline_repo, 'source_filter', lambda model, *a: model.source == 'stockdb')
    if transient:
        cached = list(db.scalars(select(Kline15m).order_by(Kline15m.ts)))
        monkeypatch.setattr(source_history, 'cached', lambda *a: cached)
    end = first + timedelta(minutes=15*100000)
    result = kline_repo.get_bars(db, '15m', 999, first, end, limit=3, offset=2, latest=True)
    assert [bar.volume for bar in result] == [99996, 99997, 99998]

import asyncio
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.data_providers.base import KlineBar
from app.models.forecast import ForecastRun, ForecastTracking
from app.models.symbol import Symbol
from app.models.user import User
from app.services import forecast_analysis as analysis, forecast_runs as runs
from app.services import local_market_sync, sync_service
from app.services.llm.providers.base import LLMResult
from app.utils.db import engine

DAY = "2026-11-05"
EVIDENCE = [{"session": DAY, "feature": "ema20"}]
DIAGNOSIS = {"regime": "tight_channel", "bias": "up", "summary": "窄通道延续", "evidence": EVIDENCE}
PREDICTION = {
    "next_candle": {"direction": "up", "reason": "收盘延续", "evidence": EVIDENCE},
    "next_regime": {"regime": "undetermined", "reason": "下一阶段信号冲突", "evidence": []},
}


def snapshot(session=DAY, version="a", count=40):
    return {
        "symbol": {"code": "600519"}, "latest_session": session, "as_of": "2026-11-05T16:00:00+08:00",
        "source": "stockdb", "data_version": version, "feature_version": 1,
        "status": "ready" if count >= 40 else "insufficient_history", "bar_count": count, "minimum_bars": 40,
        "rows": [{"ts": session, "open": 10, "high": 12, "low": 9, "close": 11, "volume": 100,
                  "amount": 1100, "forecast_features": {"ema20": 10.5, "atr14": None}}],
    }


class Model:
    available = True

    def __init__(self, *answers):
        self.answers = iter(answers)
        self.messages = []

    async def ainvoke(self, messages, temperature=None):
        self.messages.append(list(messages))
        return LLMResult(json.dumps(next(self.answers)), "test-model", model_revision="test-revision")


def test_model_rules_and_grounding():
    model = Model(DIAGNOSIS, PREDICTION)
    diagnosis, info = asyncio.run(analysis.diagnose(model, snapshot()))
    result, _ = asyncio.run(analysis.predict(model, snapshot(), diagnosis))
    assert diagnosis["evidence"][0]["value"] == 10.5
    assert info["revision"] == "test-revision"
    assert analysis.PLAYBOOK["tight_channel"] in model.messages[1][0]["content"]
    assert result["next_candle"]["direction"] == "up"
    assert result["next_regime"]["regime"] == "undetermined"


@pytest.mark.parametrize("session,feature", [("2026-11-06", "ema20"), (DAY, "atr14"), (DAY, "invented")])
def test_invalid_evidence_is_rejected(session, feature):
    response = {**DIAGNOSIS, "evidence": [{"session": session, "feature": feature}]}
    with pytest.raises(ValueError, match="evidence"):
        asyncio.run(analysis.diagnose(Model(response, response), snapshot()))


@pytest.mark.parametrize("bad_output", [
    {**DIAGNOSIS, "evidence": [{**EVIDENCE[0], "reason": "2026-11-06 收盘 999"}]},
    {**DIAGNOSIS, "summary": "2026-11-06 收盘 999"},
])
def test_model_cannot_supply_unverified_dates_or_values(bad_output):
    model = Model(bad_output, {**DIAGNOSIS, "summary": "收盘位于 EMA20 上方"})
    result, _ = asyncio.run(analysis.diagnose(model, snapshot()))
    assert len(model.messages) == 2
    assert result["summary"] == "收盘位于 EMA20 上方"
    assert result["evidence"] == [{**EVIDENCE[0], "value": 10.5}]


def test_model_can_repair_nonliteral_evidence_once():
    invalid = {**DIAGNOSIS, "evidence": [{**EVIDENCE[0], "feature": "均线上方"}]}
    model = Model(invalid, DIAGNOSIS)
    result, _ = asyncio.run(analysis.diagnose(model, snapshot()))
    assert len(model.messages) == 2
    assert model.messages[-1][-1]["role"] == "user"
    assert result["evidence"][0]["feature"] == "ema20"


def test_model_gets_the_invalid_date_and_field_during_repair():
    invalid = {**DIAGNOSIS, "evidence": [{**EVIDENCE[0], "session": "2026-11-06"}]}
    model = Model(invalid, DIAGNOSIS)
    result, _ = asyncio.run(analysis.diagnose(model, snapshot()))
    feedback = model.messages[-1][-1]["content"]
    assert "2026-11-06 的 ema20" in feedback
    assert result["evidence"][0]["session"] == DAY


@pytest.fixture
def db_factory(monkeypatch):
    with engine.connect() as connection, connection.begin() as tx:
        # Exercise the migration and ORM in a schema rolled back after the test.
        schema = f"test_forecast_{uuid4().hex}"
        connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
        connection.exec_driver_sql(f"SET LOCAL search_path TO {schema}, public")
        connection.exec_driver_sql("CREATE TABLE users (LIKE public.users INCLUDING ALL)")
        connection.exec_driver_sql("CREATE TABLE symbols (LIKE public.symbols INCLUDING ALL)")
        connection.exec_driver_sql("CREATE TABLE user_watchlist (LIKE public.user_watchlist INCLUDING ALL)")
        connection.exec_driver_sql("CREATE TABLE kline_1d (LIKE public.kline_1d INCLUDING ALL)")
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from runpy import run_path
        with Operations.context(MigrationContext.configure(connection)):
            run_path("alembic/versions/0036_forecast_runs.py")["upgrade"]()
            run_path("alembic/versions/0037_forecast_delivery.py")["upgrade"]()

        def factory():
            return Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")

        monkeypatch.setattr(runs, "get_session", factory)
        with factory() as db:
            user = User(id=9912301, username="forecast-test", password_hash="test")
            db.add(user)
            db.commit()
        yield factory, user.id
        tx.rollback()


def make_tracking_due(factory):
    with factory() as db:
        db.execute(update(ForecastTracking).values(next_check_at=datetime.now(UTC) - timedelta(seconds=1)))
        db.commit()


def test_manual_and_automatic_share_dedup_and_store_result(db_factory, monkeypatch):
    factory, user_id = db_factory
    model = Model(DIAGNOSIS, PREDICTION)
    submitted = []
    current = snapshot()
    latest = date.fromisoformat(DAY)
    monkeypatch.setattr(runs, "_publish", submitted.append)
    monkeypatch.setattr(runs, "build_llm_service_for_user", lambda *_: model)
    monkeypatch.setattr(runs.forecast_snapshot, "build_snapshot", lambda *_, **kwargs: current)
    monkeypatch.setattr(runs.forecast_snapshot, "resolve_stock", lambda *_: SimpleNamespace(id=1))
    monkeypatch.setattr(runs.forecast_snapshot, "latest_confirmed_session", lambda *_: latest)
    now = datetime.now(UTC)

    with factory() as db:
        runs.set_tracking(db, user_id, "600519", True)
    make_tracking_due(factory)
    runs._track_one(*runs._claim_due_tracking(), now, {})
    assert submitted == []
    latest = latest + timedelta(days=1)
    current = snapshot(latest.isoformat(), "b")
    make_tracking_due(factory)
    runs._track_one(*runs._claim_due_tracking(), now, {})
    make_tracking_due(factory)
    runs._track_one(*runs._claim_due_tracking(), now, {})
    with factory() as db:
        run = runs.start_manual(db, user_id, "600519")
        assert run["trigger"] == "auto"
        assert runs.history(db, user_id + 1, "600519") == {"runs": [], "tracking": False}
    assert submitted == [run["id"]]
    model.answers = iter(json.loads(json.dumps(x).replace(DAY, latest.isoformat())) for x in (DIAGNOSIS, PREDICTION))
    runs.execute(run["id"])
    runs.execute(run["id"])
    assert len(model.messages) == 2
    with factory() as db:
        saved = db.scalar(select(ForecastRun))
        assert saved.status == "completed"
        assert saved.snapshot["data_version"] == "b"
        assert saved.models["prediction"]["revision"] == "test-revision"
        assert saved.prediction["next_candle"]["evidence"][0]["value"] == 10.5
        assert db.get(ForecastTracking, (user_id, "600519")).last_session == latest
        assert "rows" not in runs.history(db, user_id, "600519")["runs"][0]["snapshot"]


def test_insufficient_data_completes_without_model(db_factory, monkeypatch):
    factory, user_id = db_factory
    monkeypatch.setattr(runs.forecast_snapshot, "build_snapshot", lambda *_: snapshot(count=3))
    with factory() as db:
        result = runs.start_manual(db, user_id, "600519")
        assert result["status"] == "completed"
        assert result["prediction"]["next_candle"]["direction"] == "undetermined"
        assert result["models"] == {}


def test_forecast_only_symbol_is_selected_and_thin_close_is_recorded(db_factory, monkeypatch):
    factory, user_id = db_factory
    stamp = datetime(2024, 1, 3, tzinfo=UTC)
    old_bar = KlineBar(stamp - timedelta(days=1), 10, 12, 9, 11, 100, 1100, close_confirmed=True)
    provisional = KlineBar(stamp, 11, 12, 10, 12, 100, 1200)
    bars = [old_bar, provisional]
    monkeypatch.setattr(sync_service, "get_provider", lambda: SimpleNamespace(
        fetch_kline_checked=lambda *_: (bars, False),
    ))
    monkeypatch.setattr(runs.forecast_snapshot, "_features", lambda rows, *_: (rows, rows[-1]["ts"]))
    monkeypatch.setattr(runs, "_publish", lambda _: pytest.fail("thin history must not call the model"))
    with factory() as db:
        symbol = Symbol(id=1, code="600519", name="Tracked only", type="stock", market="SSE")
        db.add(symbol)
        db.add(Symbol(id=2, code="600519", name="Other instrument", type="index", market="SSE"))
        db.commit()
        sync_service.prepare_history_window(db, symbol, "1d", old_bar.ts, stamp, initial=True)
        runs.set_tracking(db, user_id, "600519", True)
        assert [(sym.name, regular) for sym, regular in local_market_sync._sync_targets(db)] == [
            ("Tracked only", False),
        ]

    make_tracking_due(factory)
    runs.sweep()
    with factory() as db:
        assert db.scalar(select(ForecastRun.id)) is None
        bars[-1] = replace(provisional, close_confirmed=True)
        symbol = db.get(Symbol, 1)
        sync_service.prepare_history_window(db, symbol, "1d", old_bar.ts, stamp, initial=True)
    make_tracking_due(factory)
    runs.sweep()
    make_tracking_due(factory)
    runs.sweep()
    with factory() as db:
        result = db.scalars(select(ForecastRun)).one()
        assert result.trigger == "auto"
        assert result.status == "completed"
        assert result.prediction["next_candle"]["direction"] == "undetermined"
        assert db.get(ForecastTracking, (user_id, "600519")).last_session == stamp.date()


def test_retry_targets_owned_failed_snapshot_even_after_new_success(db_factory, monkeypatch):
    from app.core.exceptions import ApiError

    factory, user_id = db_factory
    submitted = []
    monkeypatch.setattr(runs, "_publish", submitted.append)
    with factory() as db:
        old = ForecastRun(user_id=user_id, symbol="600519", data_version="old", status="failed", trigger="auto",
                          snapshot=snapshot(version="old"), error="previous failure")
        new = ForecastRun(user_id=user_id, symbol="600519", data_version="new", status="completed", trigger="manual",
                          snapshot=snapshot(session="2026-11-06", version="new"))
        db.add_all([old, new])
        db.commit()
        with pytest.raises(ApiError) as error:
            runs.retry(db, user_id + 1, old.id)
        assert error.value.status_code == 404
        db.rollback()
        assert runs.retry(db, user_id, new.id)["status"] == "completed"
        result = runs.retry(db, user_id, old.id)
        assert result["id"] == old.id
        assert result["snapshot"]["data_version"] == "old"
        assert result["status"] == "queued"
        assert result["trigger"] == "auto"
        assert runs.retry(db, user_id, old.id)["status"] == "queued"
        assert submitted == [old.id]


def test_delivery_retries_failure_but_does_not_duplicate_an_active_message(db_factory, monkeypatch):
    from app.worker.tasks.forecast_tasks import run_forecast

    factory, user_id = db_factory
    attempts = []

    def send(**options):
        attempts.append(options)
        if len(attempts) == 1:
            raise ConnectionError("broker unavailable")

    monkeypatch.setattr(run_forecast, "apply_async", send)
    monkeypatch.setattr(runs.forecast_snapshot, "build_snapshot", lambda *_: snapshot())
    with factory() as db:
        run_id = runs.start_manual(db, user_id, "600519")["id"]
    runs.sweep()
    assert len(attempts) == 1

    with factory() as db:
        run = db.get(ForecastRun, run_id)
        run.next_delivery_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    runs.sweep()
    with factory() as db:
        run = db.get(ForecastRun, run_id)
        assert run.next_delivery_at == attempts[-1]["expires"]
        run.updated_at = datetime.now(UTC) - timedelta(minutes=10)
        db.commit()
    runs.sweep()
    assert len(attempts) == 2


def test_sweep_leaves_unvisited_subscriptions_due(db_factory, monkeypatch):
    factory, user_id = db_factory
    due = datetime.now(UTC) - timedelta(minutes=1)
    with factory() as db:
        db.add_all([ForecastTracking(user_id=user_id, symbol=code, next_check_at=due)
                    for code in ("600519", "600520")])
        db.commit()
    ticks = iter([0, 1, 60])
    monkeypatch.setattr(runs, "monotonic", lambda: next(ticks))
    visited = []

    def slow_check(user_id, symbol, previous, lease, now, snapshots):
        visited.append(symbol)
        raise TimeoutError

    monkeypatch.setattr(runs, "_track_one", slow_check)
    runs.sweep()
    with factory() as db:
        assert visited == ["600519"]
        assert db.get(ForecastTracking, (user_id, "600519")).next_check_at > due
        assert db.get(ForecastTracking, (user_id, "600520")).next_check_at == due

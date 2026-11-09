import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.forecast import ForecastRun, ForecastTracking
from app.models.user import User
from app.services import forecast_analysis as analysis, forecast_runs as runs
from app.services.llm.providers.base import LLMResult
from app.utils.db import engine

DAY = "2026-11-05"
EVIDENCE = [{"session": DAY, "feature": "ema20", "reason": "收盘位于均线之上"}]
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
        self.messages.append(messages)
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
    response = {**DIAGNOSIS, "evidence": [{"session": session, "feature": feature, "reason": "证据"}]}
    with pytest.raises(ValueError, match="evidence"):
        asyncio.run(analysis.diagnose(Model(response), snapshot()))


@pytest.fixture
def db_factory(monkeypatch):
    with engine.connect() as connection, connection.begin() as tx:
        # Exercise the migration and ORM in a schema rolled back after the test.
        schema = f"test_forecast_{uuid4().hex}"
        connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
        connection.exec_driver_sql(f"SET LOCAL search_path TO {schema}, public")
        connection.exec_driver_sql("CREATE TABLE users (LIKE public.users INCLUDING ALL)")
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from runpy import run_path
        with Operations.context(MigrationContext.configure(connection)):
            run_path("alembic/versions/0036_forecast_runs.py")["upgrade"]()

        def factory():
            return Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")

        monkeypatch.setattr(runs, "get_session", factory)
        with factory() as db:
            user = User(id=9912301, username="forecast-test", password_hash="test")
            db.add(user)
            db.commit()
        yield factory, user.id
        tx.rollback()


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
    runs._track_one(user_id, "600519", latest, now, {})
    assert submitted == []
    latest = latest + timedelta(days=1)
    current = snapshot(latest.isoformat(), "b")
    runs._track_one(user_id, "600519", date.fromisoformat(DAY), now, {})
    runs._track_one(user_id, "600519", date.fromisoformat(DAY), now, {})
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

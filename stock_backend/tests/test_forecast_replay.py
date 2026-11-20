import asyncio
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.core.exceptions import ApiError
from app.services import forecast_replay as replay
from app.services.llm.llm_service import LLMAuthError


def market():
    return [
        {"ts": (date(2024, 1, 1) + timedelta(days=i)).isoformat(),
         "open": 10, "high": 11, "low": 9, "close": 10, "volume": 10, "amount": 100}
        for i in range(50)
    ]


def test_future_factors_and_bars_never_change_an_earlier_input():
    rows = market()
    original, label = replay._case(rows, [], 39)
    rows[40] = {**rows[40], "close": 20, "high": 20}
    history, changed = replay._case(rows, [(int(rows[40]["ts"].replace("-", "")), 2.0)], 39)
    assert history == original == rows[:40]
    assert label["actual_direction"] == "flat"
    assert changed["actual_direction"] == "up"
    next_history, _ = replay._case(rows, [(int(rows[40]["ts"].replace("-", "")), 2.0)], 40)
    assert next_history[-2]["close"] == 5
    assert next_history[-1]["close"] == 20


def test_five_bar_label_and_coverage_are_independent_of_direction():
    rows = market()
    for bar in rows[40:45]:
        bar.update(close=13, high=13)
    _, first = replay._case(rows, [], 39)
    _, last = replay._case(rows, [], 48)
    assert first["actual_regime"] == "breakout" and first["previous_regime"] == "range"
    assert last["actual_direction"] == "flat" and last["actual_regime"] is None
    first.update(direction="undetermined", regime="breakout")
    last.update(direction="flat")
    scores = replay._scores([first, last])
    assert scores["direction"] == {"labelled": 2, "covered": 1, "hits": 1}
    assert scores["regime"] == {"labelled": 1, "covered": 1, "hits": 1}
    assert scores["always_up"] == {"labelled": 2, "covered": 2, "hits": 1}
    matched = replay._matched_scores([first, last])
    assert matched["always_up"] == {"count": 1, "ai_hits": 1, "baseline_hits": 0}
    assert matched["previous_regime"] == {"count": 1, "ai_hits": 1, "baseline_hits": 0}


def test_market_reads_five_traded_sessions_across_a_long_suspension(monkeypatch):
    end = date(2024, 1, 5)
    resumed = date(2024, 2, 23)
    prior = [end - timedelta(days=i) for i in range(30, -1, -1)]
    dates = [*(day for day in prior if day.weekday() < 5),
             resumed, *(resumed + timedelta(days=i) for i in range(3, 8))]
    provider = SimpleNamespace(
        daily_confirmation_cutoff=lambda _: datetime(2025, 1, 1, tzinfo=UTC),
        adjustment_timeline=lambda _: [],
        latest_day=lambda _: dates[-1],
        raw_daily_history=lambda code, start, stop: (
            {"date": int(day.strftime("%Y%m%d")), "code": code, "open": 10, "high": 12,
             "low": 9, "close": 11, "volume": 1000, "amount": 10000}
            for day in dates if start <= day <= stop
        ),
    )
    monkeypatch.setattr(replay, "StockDBProvider", lambda: provider)
    rows, timeline, _ = replay._read_market("600519", end)
    history, case = replay._case(rows, timeline, len(rows) - replay.HORIZON - 1)
    assert history[-1]["ts"] == end.isoformat()
    assert case["next_session"] == resumed.isoformat()
    assert case["actual_direction"] == "up"
    assert case["actual_regime"] == "range"
    assert case["regime_through"] == dates[-2].isoformat()
    assert len(rows) - len(history) == replay.HORIZON


@pytest.fixture
def replay_job(monkeypatch):
    rows = market()
    monkeypatch.setattr(replay, "_read_market", lambda *_: (rows, [], "market-version"))
    monkeypatch.setattr(replay, "_reconstructed", lambda history: {
        "rows": history, "feature_version": 1, "data_version": "input-version",
    })
    def service(*_, isolate_user_breaker):
        assert isolate_user_breaker
        return SimpleNamespace(available=True)
    monkeypatch.setattr(replay, "build_llm_service_for_user", service)
    class Session:
        def __enter__(self): return self
        def __exit__(self, *_): pass
    monkeypatch.setattr(replay, "get_session", Session)
    job = SimpleNamespace(id=1, user_id=1, symbol="600519",
                          options={"end": None, "samples": 3, "mode": "reconstructed"})
    return job, rows


def test_worker_replays_in_order_and_never_passes_the_labels(monkeypatch, replay_job):
    job, rows = replay_job
    seen = []

    async def predict(_, snapshot, user_id):
        assert user_id == job.user_id
        assert set(snapshot) == {"rows", "feature_version", "data_version"}
        seen.append(snapshot["rows"][-1]["ts"])
        return {"direction": "flat", "regime": "undetermined"}

    monkeypatch.setattr(replay, "_predict_case", predict)
    monkeypatch.setattr(replay, "_save", lambda *_: True)
    report = {"cases": []}
    replay._evaluate(job, report)
    assert seen == [row["ts"] for row in rows[42:45]]
    assert report["scores"]["direction"]["hits"] == 3
    assert report["scores"]["regime"]["covered"] == 0


def test_invalid_key_fails_the_job_after_one_attempt(monkeypatch, replay_job):
    job, _ = replay_job
    calls, saves = [], []

    async def invalid_key(*_):
        calls.append(True)
        raise LLMAuthError("API Key 无效")

    monkeypatch.setattr(replay, "_predict_case", invalid_key)
    monkeypatch.setattr(replay, "_save", lambda *args: saves.append(args))
    report = {"cases": []}
    replay._evaluate(job, report)
    assert len(calls) == 1
    assert saves[-1][2:] == ("failed", "API Key 无效")
    assert report["cases"][0]["status"] == "failed"


def test_account_deletion_during_diagnosis_blocks_the_next_model_call(monkeypatch):
    class Session:
        active = True

        def __enter__(self): return self
        def __exit__(self, *_): pass
        def scalar(self, _): return 1 if self.active else None

    session = Session()
    monkeypatch.setattr(replay, "get_session", lambda: session)

    async def diagnose(*_):
        session.active = False
        return {}, {}

    async def predict(*_):
        pytest.fail("deleted account must not reach the prediction stage")

    monkeypatch.setattr(replay.forecast_analysis, "diagnose", diagnose)
    monkeypatch.setattr(replay.forecast_analysis, "predict", predict)
    with pytest.raises(ApiError) as error:
        asyncio.run(replay._predict_case(None, {}, 1))
    assert error.value.status_code == 403


def test_old_report_gets_matched_scores_from_its_saved_cases():
    _, case = replay._case(market(), [], 39)
    case["direction"] = "flat"
    report = {"cases": [case], "scores": replay._scores([case])}
    row = SimpleNamespace(id=1, status="completed", options={}, report=report, error=None)
    assert replay._response(row)["report"]["matched_scores"]["last_candle"] == {
        "count": 1, "ai_hits": 1, "baseline_hits": 1,
    }
    assert "matched_scores" not in report


def test_archive_rejects_backdated_snapshot_and_preserves_first_same_day():
    row = market()[39]
    session = row["ts"]
    stamp = datetime.fromisoformat(session).replace(hour=8, tzinfo=UTC)
    snapshot = {"latest_session": session, "as_of": stamp.isoformat(),
                "status": "ready", "rows": [row]}
    future = {**snapshot, "data_version": "later"}
    saved = {**snapshot, "data_version": "same-day"}
    db = SimpleNamespace(execute=lambda _: [(future, stamp + timedelta(days=1)), (saved, stamp),
                                            ({**snapshot, "data_version": "revision"}, stamp)])
    assert replay._archived_inputs(db, 1, "600519", [session]) == {session: saved}

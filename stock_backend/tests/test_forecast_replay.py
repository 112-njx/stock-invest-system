from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from app.services import forecast_replay as replay


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


def test_worker_replays_in_order_and_never_passes_the_labels(monkeypatch):
    rows = market()
    monkeypatch.setattr(replay, "_read_market", lambda *_: (rows, [], "market-version"))
    monkeypatch.setattr(replay, "_reconstructed", lambda history: {
        "rows": history, "feature_version": 1, "data_version": "input-version",
    })
    monkeypatch.setattr(replay, "build_llm_service_for_user", lambda *_: SimpleNamespace(available=True))
    class Session:
        def __enter__(self): return self
        def __exit__(self, *_): pass
    monkeypatch.setattr(replay, "get_session", Session)
    seen = []

    async def predict(_, snapshot):
        assert set(snapshot) == {"rows", "feature_version", "data_version"}
        seen.append(snapshot["rows"][-1]["ts"])
        return {"direction": "flat", "regime": "undetermined"}

    monkeypatch.setattr(replay, "_predict_case", predict)
    monkeypatch.setattr(replay, "_save", lambda *_: True)
    job = SimpleNamespace(id=1, user_id=1, symbol="600519",
                          options={"end": None, "samples": 3, "mode": "reconstructed"})
    report = {"cases": []}
    replay._evaluate(job, report)
    assert seen == [row["ts"] for row in rows[42:45]]
    assert report["scores"]["direction"]["hits"] == 3
    assert report["scores"]["regime"]["covered"] == 0


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

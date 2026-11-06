"""Causal swing calculations, checkpoint replay, breadth and volume regressions."""

from contextlib import nullcontext
from threading import Event
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from app.services import stockdb_service as rd
from app.services import trend_service as service
from app.services.indicators.macd import MACDIndicator
from app.services.trend_engine import TrendState


def advance(state, prices, start=20260101):
    return [state.advance(start + i, price, 100, (price / prices[i - 1] - 1) * 100 if i else 0)
            for i, price in enumerate(prices)]


def test_reversal_is_confirmed_on_second_opposite_day_without_repainting():
    state = TrendState()
    cells = advance(state, [100, 101, 102, 103, 102, 104, 103, 102, 103, 104, 105])
    assert [cell["wave"] for cell in cells] == [0, 0, 1, 2, 3, 4, 5, -1, -2, 1, 2]
    assert [cell["signals"] for cell in cells] == ["", "", "", "B", "", "", "", "S", "", "", "B"]
    assert cells[6]["wave"] == 5
    assert state.base_date == 20260109
    assert state.metrics(1)["return"] == pytest.approx((105 / 103 - 1) * 100)


def test_flat_session_breaks_pending_reversal():
    state = TrendState()
    cells = advance(state, [100, 101, 101, 102, 103, 102, 102, 101])
    assert [cell["wave"] for cell in cells] == [0, 0, 0, 0, 1, 2, 3, 4]


def test_volume_signal_requires_positive_day_and_full_twenty_session_history():
    state = TrendState()
    assert "V" not in advance(state, list(range(100, 120)))[-1]["signals"]
    cell = state.advance(20260121, 120, 101, 1)
    assert cell["signals"] == "V"
    assert "V" not in state.advance(20260122, 119, 500, -1)["signals"]
    assert "V" not in state.advance(20260123, 121, 200, 1)["signals"]


def test_macd_matches_existing_indicator_and_adjustment_scale():
    prices = [100 + i * .2 + np.sin(i) for i in range(60)]
    state = TrendState()
    advance(state, prices)
    expected = MACDIndicator().calculate(pd.DataFrame({"close": np.array(prices) / 2}))
    metrics = state.metrics(2)
    assert metrics["dif"] == pytest.approx(expected.iloc[-1]["macd_dif"])
    assert metrics["dea"] == pytest.approx(expected.iloc[-1]["macd_dea"])
    assert metrics["macd"] == pytest.approx(expected.iloc[-1]["macd_hist"])


def test_repeated_or_out_of_order_sessions_are_rejected():
    state = TrendState()
    state.advance(20260102, 100, 100, 0)
    with pytest.raises(ValueError):
        state.advance(20260102, 101, 100, 1)


@pytest.fixture
def history(monkeypatch):
    dates = [20260101, 20260102, 20260105, 20260106]
    stocks = {"600001": {"name": "样本甲"}, "600002": {"name": "样本乙"}}
    boards = {"sw1": {"code": "sw1", "name": "测试行业", "category": "申万一级", "symbols": list(stocks)}}
    base = rd.Snapshot(dates, boards, stocks, np.empty((0, 0, 0)), {}, "local-v1")
    rows = []
    for code in stocks:
        for date, close in zip([20251229, 20251230, 20251231, *dates], [100, 101, 102, 103, 104, 103, 102], strict=True):
            if code == "600002" and date == 20260105:
                continue
            rows.append([date, code, close, close - 1, 100, 1])
    calls = []

    def read(client, command, table, **params):
        if table == "复权*":
            return []
        calls.append(params["k2"])
        start, end = map(int, params["k2"].removeprefix("fwd:").split(","))
        selected = [row.copy() for row in rows if start <= row[0] <= end and row[1].startswith(params["k1"][-1])]
        return [None, [None] * 6, *reversed(selected)]

    monkeypatch.setattr(rd, "_client", lambda: nullcontext(None))
    monkeypatch.setattr(rd, "_rd", read)
    monkeypatch.setattr(service, "_stop", Event())
    return base, rows, calls


def test_checkpoint_replay_matches_complete_history_and_suspension_does_not_count(history):
    base, _, calls = history
    full = service._build(base, None, lambda: None)
    assert full["checkpoint"]["600001"]["age"] == 1
    first = full["stocks"][0]
    by_code = {stock["code"]: stock for stock in full["stocks"]}
    assert [cell["wave"] if cell else None for cell in by_code["600002"]["cells"]] == [2, 3, None, 4]
    assert [cell["wave"] for cell in by_code["600001"]["cells"]] == [2, 3, 4, -1]
    assert full["breadth"] == [2, 2, 2, 0]
    assert first["code"] == "600002"
    calls.clear()
    replayed = service._build(base, full, lambda: None)
    assert replayed["version"] == full["version"]
    assert replayed["stocks"] == full["stocks"]
    assert all(query == "fwd:20260101,20260106" for query in calls)


def test_persisted_checkpoint_can_resume_before_first_complete_snapshot(history):
    base, _, calls = history
    saved = []
    full = service._build(base, None, lambda: None, saved.append)
    assert len(saved) == 1
    assert "stocks" not in saved[0]
    calls.clear()
    resumed = service._build(base, saved[0], lambda: None)
    assert resumed["version"] == full["version"]
    assert resumed["stocks"] == full["stocks"]
    assert all(query == "fwd:20260101,20260106" for query in calls)


def test_same_day_history_correction_changes_snapshot_version(history):
    base, rows, _ = history
    original = service._build(base, None, lambda: None)
    rows[-1][2] = 106
    corrected = service._build(base, original, lambda: None)
    assert corrected["dates"] == original["dates"]
    assert corrected["version"] != original["version"]


def test_industry_filter_keeps_global_breadth_and_uses_pool_average(history):
    base, _, _ = history
    data = service._build(base, None, lambda: None)
    all_stocks = service.overview(data, "all")
    industry = service.overview(data, "sw1")
    assert industry["breadth"] == all_stocks["breadth"]
    assert industry["average"] == all_stocks["average"]
    assert len(industry["stocks"]) == 2


def test_failed_update_retains_complete_cached_matrix(monkeypatch):
    cached = {"schema": 1, "version": "valid", "builtAt": 0}
    monkeypatch.setattr(service, "_data", cached)
    monkeypatch.setattr(service, "_restore", lambda: cached)
    monkeypatch.setattr(rd, "snapshot", Mock(side_effect=rd.StockDBError("RD offline")))
    service._update()
    assert service._data is cached
    assert service.status()["ready"] is True

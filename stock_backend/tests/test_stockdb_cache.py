"""Regression coverage for stale serving, atomic refresh, persistence and versioned responses."""

import json
from contextlib import nullcontext
from datetime import date, timedelta
from threading import Lock
from time import time
from unittest.mock import Mock

import numpy as np
import pytest
from app.api.v1 import stockdb
from app.services import stockdb_cache as cache
from app.services import stockdb_service as rd
from fastapi import FastAPI
from fastapi.testclient import TestClient


def sample(version="v2-original"):
    return rd.Snapshot(
        dates=[20261103, 20261104], boards={}, stocks={},
        values=np.zeros((0, 2, 9)), positions={}, version=version,
    )


@pytest.fixture
def isolated(monkeypatch):
    previous = sample()
    redis = Mock()
    redis.set.return_value = True
    monkeypatch.setattr(cache, "_snapshot", previous)
    monkeypatch.setattr(cache, "_built_at", time() - 1000)
    monkeypatch.setattr(cache, "_last_error", "")
    monkeypatch.setattr(cache, "_refresh_lock", Lock())
    monkeypatch.setattr(cache, "_state", lambda: None)
    monkeypatch.setattr(cache, "_shared_get", lambda key: None)
    monkeypatch.setattr(cache, "get_redis_client", lambda: redis)
    return previous, redis


def test_expired_snapshot_is_served_without_waiting_for_rd(isolated, monkeypatch):
    previous, _ = isolated
    refresh = Mock()
    monkeypatch.setattr(cache, "refresh", refresh)
    monkeypatch.setattr(rd, "_load_snapshot", Mock(side_effect=AssertionError("must run in background")))
    assert cache.get_snapshot() is previous
    refresh.assert_called_once_with()


def test_failed_refresh_keeps_previous_complete_generation(isolated, monkeypatch):
    previous, _ = isolated
    monkeypatch.setattr(rd, "_load_snapshot", Mock(side_effect=rd.StockDBError("RD offline")))
    cache._rebuild(force=True)
    assert cache._snapshot is previous
    assert cache._last_error == "RD offline"
    assert not cache._refresh_lock.locked()


def test_first_screen_failure_does_not_publish_partial_generation(isolated, monkeypatch):
    previous, redis = isolated
    candidate = sample("v2-new")
    monkeypatch.setattr(rd, "_load_snapshot", lambda: candidate)
    monkeypatch.setattr(cache, "warm_home", Mock(side_effect=ValueError("incomplete home")))
    cache._rebuild(force=True)
    assert cache._snapshot is previous
    assert "incomplete home" in cache._last_error
    # Only the lease was acquired. No snapshot blob or state pointer was written.
    assert redis.set.call_count == 1


def test_successful_refresh_publishes_warmed_generation(isolated, monkeypatch):
    _, redis = isolated
    candidate = sample("v2-new")
    warmed = []
    monkeypatch.setattr(rd, "_load_snapshot", lambda: candidate)
    monkeypatch.setattr(cache, "warm_home", warmed.append)
    cache._rebuild(force=True)
    assert cache._snapshot is candidate
    assert warmed == [candidate]
    assert any("snapshot:v2-new" in call.args[0] for call in redis.set.call_args_list)


def test_persisted_snapshot_restores_without_rd_read(isolated, monkeypatch):
    previous, _ = isolated
    packed = cache._pack(previous)
    monkeypatch.setattr(cache, "_snapshot", None)
    monkeypatch.setattr(cache, "_state", lambda: {"version": previous.version, "built_at": time()})
    monkeypatch.setattr(cache, "_shared_get", lambda key: packed if key.startswith("snapshot:") else None)
    monkeypatch.setattr(cache, "warm_home", lambda data: None)
    monkeypatch.setattr(rd, "_load_snapshot", Mock(side_effect=AssertionError("should restore")))
    cache._rebuild()
    assert cache._snapshot.version == previous.version
    np.testing.assert_equal(cache._snapshot.values, previous.values)


def test_expired_persisted_snapshot_survives_offline_source_after_restart(isolated, monkeypatch):
    previous, _ = isolated
    packed = cache._pack(previous)
    monkeypatch.setattr(cache, "_snapshot", None)
    monkeypatch.setattr(cache, "_state", lambda: {"version": previous.version, "built_at": time() - 600})
    monkeypatch.setattr(cache, "_shared_get", lambda key: packed if key.startswith("snapshot:") else None)
    monkeypatch.setattr(rd, "_load_snapshot", Mock(side_effect=rd.StockDBError("RD offline")))
    cache._rebuild()
    assert cache._snapshot.version == previous.version
    assert cache._last_error == "RD offline"


def test_startup_restores_expired_snapshot_and_refreshes_in_background(isolated, monkeypatch):
    previous, _ = isolated
    monkeypatch.setattr(cache, "_snapshot", None)
    monkeypatch.setattr(cache, "_state", lambda: {"version": previous.version, "built_at": time() - 600})
    packed = cache._pack(previous)
    monkeypatch.setattr(cache, "_shared_get", lambda key: packed if key.startswith("snapshot:") else None)
    monkeypatch.setattr(cache, "warm_home", Mock())
    refresh = Mock()
    monkeypatch.setattr(cache, "refresh", refresh)
    monkeypatch.setattr(rd, "_load_snapshot", Mock(side_effect=AssertionError("must run in background")))
    cache.prepare()
    assert cache._snapshot.version == previous.version
    refresh.assert_called_once_with()


@pytest.mark.parametrize(("candidate_version", "expected_deleted"), [("A", None), ("C", "A")])
def test_generation_cleanup_preserves_active_and_previous_versions(
    isolated, monkeypatch, candidate_version, expected_deleted,
):
    _, redis = isolated
    redis.eval.return_value = 1
    monkeypatch.setattr(cache, "_state", lambda: {"version": "B", "previous": "A", "built_at": time() - 600})
    monkeypatch.setattr(cache, "warm_home", Mock())
    monkeypatch.setattr(rd, "_load_snapshot", lambda: sample(candidate_version))
    cache._rebuild(force=True)
    assert cache._snapshot.version == candidate_version
    if expected_deleted is None:
        redis.delete.assert_not_called()
    else:
        redis.delete.assert_called_once_with(cache._namespace + ":snapshot:" + expected_deleted)


def test_corrupt_shared_blob_can_be_rebuilt(isolated, monkeypatch):
    previous, _ = isolated
    monkeypatch.setattr(cache, "_shared_get", lambda key: "invalid archive")
    assert cache._restore({"version": "different", "built_at": time()}) is False
    assert cache._snapshot is previous


def test_ranking_and_etag_do_not_send_full_curves(monkeypatch):
    data = sample()
    data.category = lambda category, weight: [{
        "id": "801081.SL", "name": "半导体", "count": 176,
        "bars": [[20261104, 1, 2, 1, 2, 10, 20, 1]],
    }]
    monkeypatch.setattr(rd, "snapshot", lambda: data)
    monkeypatch.setattr(cache, "response_bytes", lambda data, key, build: json.dumps(build()).encode())
    app = FastAPI()
    app.include_router(stockdb.router)
    with TestClient(app) as client:
        response = client.get("/api/v1/stockdb/ranking")
        assert response.status_code == 200
        board = response.json()["boards"][0]
        assert "bars" not in board
        assert board["changes"]["1"] == 100
        cached = client.get("/api/v1/stockdb/ranking", headers={"If-None-Match": response.headers["etag"]})
        assert cached.status_code == 304
        assert cached.content == b""
        assert client.get("/api/v1/stockdb/charts", params={"ids": "801081.SL", "version": "stale"}).status_code == 409


def test_content_version_changes_for_same_day_corrections(monkeypatch):
    # Same latest trading date, different raw OHLC data must invalidate caches.
    raw = [20261104, "600519", "贵州茅台", 10, 12, 9, 11, 10, 100, 1000, 2000, 3000]
    monkeypatch.setattr(rd, "_client", lambda: nullcontext(None))

    def read(client, command, table, **params):
        if command == "keys":
            return ["日k:600519:20261103", "日k:600519:20261104"]
        if table in ("板块*", "复权*"):
            return []
        return [raw.copy()] if params["k1"] == "qz:6" else []

    monkeypatch.setattr(rd, "_rd", read)
    original = rd._load_snapshot()
    raw[6] = 11.5
    corrected = rd._load_snapshot()
    assert original.dates == corrected.dates
    assert original.version != corrected.version


@pytest.mark.parametrize("length", [6, 61])
def test_phase_returns_use_factor_adjustment_and_exact_history(monkeypatch, length):
    dates = list(range(20260101, 20260101 + length))
    def query(client, command, table, **params):
        if command == "keys":
            return [f"日k:600001:{day}" for day in dates] + ["日k:600001:20990101"]
        if table == "复权":
            return [[f"复权:600001:{dates[-1]}", 2]]
        assert "num" not in params
        assert params["k2"] == f"fwd:{dates[0]},{dates[-1]}"
        return [[day, 50 if day == dates[-1] else 100] for day in dates]
    monkeypatch.setattr(rd, "_client", lambda: nullcontext(None))
    monkeypatch.setattr(rd, "_rd", query)
    result = rd.performance("600001", dates[-1])
    assert result["returns"]["5"]["value"] == 0
    assert result["returns"]["60"]["value"] == (0 if length == 61 else None)
    assert result["as_of"] == dates[-1]


def test_phase_returns_reject_missing_snapshot_day(monkeypatch):
    monkeypatch.setattr(rd, "_client", lambda: nullcontext(None))
    monkeypatch.setattr(rd, "_rd", lambda *args, **kwargs: ["日k:600001:20260101"] if args[1] == "keys" else [])
    with pytest.raises(rd.StockDBError):
        rd.performance("600001", 20260102)


def test_phase_etag_revalidates_corrections_outside_snapshot_window(monkeypatch):
    first = date(2026, 7, 1)
    days = [first + timedelta(days=i) for i in range(100)]
    dates = [int(day.strftime("%Y%m%d")) for day in days if day.weekday() < 5]
    rows = [[day, "600519", "test", 100, 100, 100, 100, 100, 10, 1000, 2000, 3000, 1]
            for day in dates]

    def query(client, command, table, **params):
        if command == "keys":
            return [f"日k:600519:{day}" for day in dates]
        if table in ("板块*", "复权*", "复权"):
            return []
        start, end = map(int, params["k2"].split(":")[1].split(","))
        selected = [row for row in rows if start <= row[0] <= end]
        if params["k1"].startswith("qz:") and params["k1"] != "qz:6":
            return []
        return [[row[0], row[6]] for row in selected] if params["ap"] == "get.date,close" else selected

    monkeypatch.setattr(rd, "_client", lambda: nullcontext(None))
    monkeypatch.setattr(rd, "_rd", query)
    original = rd._load_snapshot()
    monkeypatch.setattr(rd, "snapshot", lambda: original)
    # An existing version-keyed response must never suppress the fresh history read.
    monkeypatch.setattr(cache, "response_bytes", Mock(side_effect=AssertionError("snapshot cache used")))
    app = FastAPI()
    app.include_router(stockdb.router)
    path = f"/api/v1/stockdb/stocks/600519/performance?version={original.version}"
    with TestClient(app) as client:
        response = client.get(path)
        assert response.status_code == 200
        assert response.json()["returns"]["60"]["value"] == 0
        headers = {"If-None-Match": response.headers["etag"]}
        unchanged = client.get(path, headers=headers)
        assert unchanged.status_code == 304
        assert unchanged.content == b""

        assert rows[-61][0] < original.dates[0]
        rows[-61][6] = 50
        corrected = rd._load_snapshot()
        assert corrected.version == original.version
        response = client.get(path, headers=headers)
        assert response.status_code == 200
        assert response.json()["returns"]["60"]["value"] == 100
        assert response.headers["etag"] != headers["If-None-Match"]
        assert response.json()["version"] == original.version

        assert client.get(path.replace(original.version, "stale")).status_code == 409
        monkeypatch.setattr(rd, "performance", Mock(side_effect=rd.StockDBError("RD offline")))
        assert client.get(path, headers=headers).status_code == 503

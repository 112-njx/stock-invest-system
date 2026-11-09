from datetime import date
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.core.exceptions import ApiError
from app.data_providers.base import ProviderError
from app.services import stock_search_directory as search
from app.services import user_service


@pytest.fixture(autouse=True)
def reset_directory_cache(monkeypatch):
    monkeypatch.setattr(search, "_snapshot", None)
    monkeypatch.setattr(search, "_expires", 0)
    monkeypatch.setattr(search, "_stale", False)
    monkeypatch.setattr(search, "_refreshing", False)
    monkeypatch.setattr(search, "_initial_worker", None)


def bar(code, name="测试股票", day=20261105):
    return dict(code=code, name=name, date=day, open=10, high=12, low=9, close=11)


def test_nonblocking_cold_directory_read_schedules_only_one_refresh(monkeypatch):
    thread = Mock()
    monkeypatch.setattr(search, "Thread", thread)
    for _ in range(2):
        with pytest.raises(ApiError) as failure:
            search.get_directory(wait_for_initial=False)
        assert failure.value.status_code == 503
    thread.assert_called_once()
    thread.return_value.start.assert_called_once()


def test_first_search_shares_homepage_cold_refresh(monkeypatch):
    started, release, joining = Event(), Event(), Event()
    results = []

    class DirectoryWorker(Thread):
        def join(self, timeout=None):
            joining.set()
            return super().join(timeout)

    def slow_build(_provider):
        started.set()
        assert release.wait(3)
        return {"version": "new", "items": [bar("000001")]}

    build = Mock(side_effect=slow_build)
    monkeypatch.setattr(search, "build_directory", build)
    monkeypatch.setattr(search, "Thread", DirectoryWorker)
    with pytest.raises(ApiError):
        search.get_directory(wait_for_initial=False)
    directory_worker = search._initial_worker
    assert directory_worker is not None
    search_worker = Thread(target=lambda: results.append(search.get_directory()))
    search_worker.start()
    try:
        assert started.wait(1)
        assert joining.wait(1)
    finally:
        release.set()
        search_worker.join(3)
        directory_worker.join(3)
    assert results == [{"version": "new", "items": [bar("000001")], "stale": False}]
    assert build.call_count == 1


def test_stock_identity_retirement_and_suspended_history():
    queries = []

    def query(cmd, table, **params):
        queries.append((table, params))
        if table == "股票代码":
            return {"0": ["000001", "000002", "000003"], "5": ["510300"], "3": ["399001"], "9": ["920305"]}
        if table == "退市*":
            return ["000003"]
        if params["k1"] == "all:":
            return [bar("000001", "平安银行"), bar("000003"), bar("510300", "沪深300ETF")]
        if params["k1"] == "key:000002":
            return [bar("000002", "万科A", 20261030)]
        return []

    provider = SimpleNamespace(query=query, latest_day=lambda: date(2026, 11, 5))
    result = search.build_directory(provider)
    assert [s["code"] for s in result["items"]] == ["000001", "000002"]
    assert result["items"][0]["name"] == "平安银行"
    assert result["items"][1]["latest_date"] == "20261030"
    assert result["excluded"] == [{"code": "000003", "reason": "delisted"},
                                  {"code": "920305", "reason": "no_valid_daily_bar"}]
    assert all(s["type"] == "stock" for s in result["items"])
    assert [s["ordinal"] for s in result["items"]] == [1, 2]
    assert not any(table.startswith("分钟") for table, _ in queries)


@pytest.mark.parametrize("change", [{"close": 0}, {"high": float("nan")}, {"low": 20}, {"code": "000002"}, {"name": ""}])
def test_invalid_daily_bar_is_not_eligible(change):
    assert not search.valid_bar({**bar("000001"), **change}, "000001")


def test_outage_uses_stale_snapshot_but_empty_cache_returns_503(monkeypatch):
    monkeypatch.setattr(search, "_expires", 0)
    monkeypatch.setattr(search, "_snapshot", None)
    monkeypatch.setattr(search, "build_directory", Mock(side_effect=ProviderError("offline")))
    with pytest.raises(ApiError) as error:
        search.get_directory()
    assert error.value.status_code == 503
    monkeypatch.setattr(search, "_snapshot", {"version": "old", "items": [bar("000001")]})
    assert search.get_directory()["stale"] is True
    assert search.get_directory()["version"] == "old"


def test_stock_watchlist_identifier_does_not_resolve_same_code_index(monkeypatch):
    monkeypatch.setattr(search, "get_directory", lambda: {"items": [{"code": "000001", "name": "平安银行"}]})
    db = Mock()
    db.scalar.return_value = SimpleNamespace(id=102805)
    wrong_lookup = Mock(side_effect=AssertionError("untyped code lookup must not run"))
    monkeypatch.setattr(user_service.symbol_repo, "get_by_code", wrong_lookup)
    assert user_service._resolve_symbol_id(db, "stock:000001") == 102805
    stmt = str(db.scalar.call_args.args[0])
    assert "symbols.type =" in stmt and "symbols.code =" in stmt


def test_stock_identifier_rejects_code_not_in_local_directory(monkeypatch):
    monkeypatch.setattr(search, "get_directory", lambda: {"items": []})
    with pytest.raises(ApiError):
        user_service._resolve_symbol_id(Mock(), "stock:510300")


def test_expired_cache_returns_during_slow_single_background_refresh(monkeypatch):
    started, release = Event(), Event()
    workers = []

    def slow_build(_provider):
        started.set()
        assert release.wait(3)
        return {"version": "new", "items": [bar("000002")]}

    def worker_factory(**kwargs):
        worker = Thread(**kwargs)
        workers.append(worker)
        return worker

    monkeypatch.setattr(search, "_snapshot", {"version": "old", "items": [bar("000001")]})
    build = Mock(side_effect=slow_build)
    monkeypatch.setattr(search, "build_directory", build)
    monkeypatch.setattr(search, "Thread", worker_factory)
    try:
        result = search.get_directory()
        assert started.wait(1)
        assert result["version"] == "old" and result["stale"] is True
        # Refresh remains blocked, but readers (including watchlist resolution) do not.
        for _ in range(3):
            assert search.get_directory()["version"] == "old"
        assert build.call_count == 1
    finally:
        release.set()
        for worker in workers:
            worker.join(3)
            assert not worker.is_alive()
    assert search.get_directory() == {"version": "new", "items": [bar("000002")], "stale": False}


def test_failed_cold_cache_backs_off_instead_of_retrying_each_request(monkeypatch):
    build = Mock(side_effect=ProviderError("offline"))
    monkeypatch.setattr(search, "build_directory", build)
    for _ in range(3):
        with pytest.raises(ApiError) as error:
            search.get_directory()
        assert error.value.status_code == 503
    assert build.call_count == 1


def test_cold_refresh_does_not_hold_state_lock(monkeypatch):
    started, release = Event(), Event()
    results = []

    def slow_build(_provider):
        started.set()
        assert release.wait(3)
        return {"version": "new", "items": [bar("000001")]}

    monkeypatch.setattr(search, "build_directory", slow_build)
    worker = Thread(target=lambda: results.append(search.get_directory()))
    worker.start()
    try:
        assert started.wait(1)
        with pytest.raises(ApiError) as error:
            search.get_directory()
        assert error.value.status_code == 503
    finally:
        release.set()
        worker.join(3)
        assert not worker.is_alive()
    assert results[0]["version"] == "new"


def test_stock_insert_conflict_reuses_concurrent_creator(monkeypatch):
    monkeypatch.setattr(search, "get_directory", lambda: {
        "items": [{"code": "000001", "name": "平安银行", "market": "SZSE"}],
    })
    db = Mock()
    db.scalar.side_effect = [None, None, SimpleNamespace(id=102805)]
    assert user_service._resolve_symbol_id(db, "stock:000001") == 102805
    statement = str(db.scalar.call_args_list[1].args[0])
    assert "ON CONFLICT (type, name) DO NOTHING" in statement
    db.rollback.assert_not_called()


def test_stock_name_conflict_is_not_mistaken_for_same_code(monkeypatch):
    monkeypatch.setattr(search, "get_directory", lambda: {
        "items": [{"code": "000001", "name": "平安银行", "market": "SZSE"}],
    })
    db = Mock()
    db.scalar.side_effect = [None, None, None]
    with pytest.raises(ApiError) as error:
        user_service._resolve_symbol_id(db, "stock:000001")
    assert error.value.status_code == 409

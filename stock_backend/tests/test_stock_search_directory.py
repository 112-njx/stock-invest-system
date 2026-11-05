from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from app.core.exceptions import ApiError
from app.data_providers.base import ProviderError
from app.services import stock_search_directory as search
from app.services import user_service


def bar(code, name="测试股票", day=20261105):
    return dict(code=code, name=name, date=day, open=10, high=12, low=9, close=11)


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

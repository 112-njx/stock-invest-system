"""The management view shows only live provider requests with their K-line context."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.api.v1.admin import active_provider_requests
from app.data_providers.base import BaseDataProvider
from app.data_providers.request_activity import ActiveProviderRequest, kline_scope, list_active_requests


class StubProvider(BaseDataProvider):
    name = "eastmoney"

    def fetch_kline(self, symbol, period, start, end, asset_type="stock"):
        return []

    def fetch_realtime(self, symbols):
        return []

    def resolve_index_code(self, name):
        return None


def test_live_kline_request_has_symbol_interface_range_and_cleanup():
    task = SimpleNamespace(name="app.worker.tasks.sync_tasks.watchlist_stock_sync",
                           request=SimpleNamespace(id="activity-test-task",
                                                   delivery_info={"routing_key": "watchlist"}))
    start = datetime(2026, 8, 27, tzinfo=UTC)
    end = datetime(2026, 10, 30, tzinfo=UTC)
    with patch("celery.current_task", task), kline_scope("601398", "1d", start, end, "stock"):
        activity = ActiveProviderRequest("eastmoney", lambda: None, {"symbol": "601398"})
        try:
            activity.update("requesting", 1, 2)
            record = next(row for row in list_active_requests() if row["id"] == activity.data["id"])
            assert (record["queue"], record["symbol"], record["period"]) == ("watchlist", "601398", "1d")
            assert record["start"] == start.isoformat() and record["end"] == end.isoformat()
            db = MagicMock()
            db.scalars.return_value = [SimpleNamespace(code="601398", name="工商银行", type="stock")]
            response = active_provider_requests(current=None, db=db)
            displayed = next(row for row in response["data"]["requests"] if row["id"] == activity.data["id"])
            assert displayed["symbol_name"] == "工商银行"
        finally:
            activity.close()
    assert all(row["id"] != activity.data["id"] for row in list_active_requests())


def test_provider_call_is_visible_only_while_upstream_request_runs():
    task = SimpleNamespace(name="app.worker.tasks.sync_tasks.watchlist_stock_sync",
                           request=SimpleNamespace(id="activity-call-task",
                                                   delivery_info={"routing_key": "watchlist"}))
    provider = StubProvider()

    def upstream(**kwargs):
        records = [row for row in list_active_requests() if row["task_id"] == "activity-call-task"]
        assert len(records) == 1
        assert records[0]["phase"] == "requesting"
        assert records[0]["symbol"] == "601398"
        return "ok"

    with patch("celery.current_task", task), patch("app.data_providers.traffic.acquire"):
        with kline_scope("601398", "1d", datetime(2026, 8, 27, tzinfo=UTC),
                         datetime(2026, 10, 30, tzinfo=UTC), "stock"):
            assert provider._call(upstream, symbol="601398") == "ok"
    assert not any(row["task_id"] == "activity-call-task" for row in list_active_requests())

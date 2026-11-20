from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from app.api.deps import get_current_admin
from app.api.v1 import admin
from app.main import app
from app.services import admin_services
from fastapi.testclient import TestClient


def test_queue_list_includes_replay_and_excludes_retired_watchlist(monkeypatch):
    status = {name: lambda: {} for name in ("ping", "active_queues", "scheduled", "reserved")}
    status["active"] = lambda: {"worker": [
        {"delivery_info": {"routing_key": "forecast_replay"}},
        {"delivery_info": {"routing_key": "watchlist"}},
    ]}
    monkeypatch.setattr(admin.celery_app.control, "inspect", lambda **_: SimpleNamespace(**status))
    redis = Mock()
    redis.llen.return_value = 0
    queues, workers = admin._task_queue_state(redis)
    assert queues["forecast_replay"]["active"] == 1
    assert "watchlist" not in queues
    assert not any(workers.values())


@pytest.mark.parametrize(("payload", "params", "state", "day"), [
    (["日k:600519:20261105"], {"cmd": "keys"}, "online", "20261105"),
    ([], {"cmd": "keys"}, "online", None),
    ({"status": "ok"}, None, "online", None),
    ({"error": "not ready"}, None, "unavailable", None),
    ({"error": "bad query"}, {"cmd": "keys"}, "unavailable", None),
])
def test_local_probe_validates_response(monkeypatch, payload, params, state, day):
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.get.return_value.json.return_value = payload
    factory = Mock(return_value=client)
    monkeypatch.setattr(admin_services.httpx, "Client", factory)
    assert admin_services._probe("http://local.test/", params) == {"state": state, "latest_date": day}
    factory.assert_called_once_with(timeout=3, trust_env=False)


def test_local_probe_failure_isolated(monkeypatch):
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.get.side_effect = httpx.ConnectError("offline")
    monkeypatch.setattr(admin_services.httpx, "Client", lambda **_: client)
    assert admin_services._probe("http://local.test/")["state"] == "unavailable"


def test_local_services_requires_admin():
    with TestClient(app) as client:
        assert client.get('/api/v1/admin/local-services').status_code == 401


def test_local_services_route_preserves_probe_results(monkeypatch):
    snapshot = {"stockdb": {"state": "online", "latest_date": "20261105"},
                "sdk": {"state": "unavailable", "latest_date": None}}
    monkeypatch.setattr(admin_services, "local_service_status", lambda: snapshot)
    app.dependency_overrides[get_current_admin] = lambda: SimpleNamespace(id=1)
    try:
        with TestClient(app) as client:
            response = client.get('/api/v1/admin/local-services')
            assert response.status_code == 200
            assert response.json()["data"] == snapshot
    finally:
        app.dependency_overrides.pop(get_current_admin, None)

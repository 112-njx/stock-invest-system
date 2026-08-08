"""1.1/1.2 脚手架与可观测端点测试。"""

from fastapi.testclient import TestClient


def test_docs_accessible(client: TestClient):
    assert client.get("/docs").status_code == 200


def test_health_returns_unified_body(client: TestClient):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["msg"] == "ok"
    assert body["data"]["status"] == "alive"


def test_response_has_request_id_header(client: TestClient):
    resp = client.get("/health")
    assert resp.headers.get("X-Request-ID")


def test_ready_check(client: TestClient):
    # 未启动 Redis 时 /ready 应返回 503，DB 可用
    resp = client.get("/ready")
    assert resp.status_code in (200, 503)
    assert "db" in resp.json()["data"]


def test_metrics_expose_prometheus(client: TestClient):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "http_requests_total" in resp.text


def test_unknown_route_returns_unified_error(client: TestClient):
    resp = client.get("/api/v1/not-exist")
    assert resp.status_code == 404
    assert resp.json()["code"] != 0

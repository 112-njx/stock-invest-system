"""阶段四 4.3/4.4 回测任务流 + API 集成测试（mock K 线与 Celery，不依赖 Redis/网络）。"""

import types
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.user import User
from app.repositories import kline_repo
from app.services import backtest_service
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_bt_"

_SMA_STRATEGY = """
def initialize(context):
    context.fast = int(context.params.get("entry", {}).get("fast", 5))
def on_bar(bar, context):
    closes = context.closes
    if len(closes) < context.fast:
        return
    ma = sum(closes[-context.fast:]) / context.fast
    if bar["close"] > ma and context.pos == 0:
        context.buy()
    elif bar["close"] < ma and context.pos > 0:
        context.sell()
"""


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _register(client: TestClient, username: str) -> str:
    r = client.post("/api/v1/auth/register", json={"username": username, "password": "pass123456"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _cleanup_users(*unames: str) -> None:
    db = get_session()
    try:
        for u in unames:
            row = db.query(User).filter(User.username == u).first()
            if row:
                db.delete(row)
        db.commit()
    finally:
        db.close()


def _fake_bars(n=60):
    """合成日K：先涨后跌，60 根。"""
    bars = []
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(n):
        c = round(10 + (i if i < 30 else 60 - i) * 0.3, 3)
        bars.append(types.SimpleNamespace(ts=ts + timedelta(days=i), open=c, high=round(c + 0.1, 3), low=round(c - 0.1, 3), close=c, volume=1000, amount=round(c * 1000, 2)))
    return bars


def _create_strategy(client: TestClient, token: str) -> int:
    r = client.post(
        "/api/v1/strategies",
        json={"title": "双均线", "description": "金叉买死叉卖", "code": _SMA_STRATEGY, "params": {"entry": {"fast": 5}}, "status": "active"},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _make_mocks(monkeypatch, bars=None):
    """mock 掉 Celery delay 与 K 线源（避免 Redis/真实行情），记忆抽取 no-op。"""
    monkeypatch.setattr("app.worker.tasks.backtest_tasks.run_backtest_task", types.SimpleNamespace(delay=lambda task_id: None))
    monkeypatch.setattr(kline_repo, "get_bars", lambda db, period, symbol_id, start, end, limit=1000: (bars if bars is not None else _fake_bars()))
    monkeypatch.setattr(backtest_service, "_save_backtest_memory", lambda *a, **k: None)


# ---- 完整链路 ----
def test_backtest_full_flow(client: TestClient, monkeypatch):
    uname = _uname()
    try:
        _make_mocks(monkeypatch)
        token = _register(client, uname)
        sid = _create_strategy(client, token)

        r = client.post("/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519", "period": "1d"}, headers=_auth(token))
        assert r.status_code == 200, r.text
        task_id = r.json()["data"]["id"]
        assert r.json()["data"]["status"] == "queued"

        # 同步执行回测（模拟 worker）
        result = backtest_service.execute_backtest(task_id)
        assert result["result_id"] and result["metrics"]["total_sells"] >= 1

        # 任务状态 → success
        task = client.get(f"/api/v1/backtest/tasks/{task_id}", headers=_auth(token)).json()["data"]
        assert task["status"] == "success" and task["progress"] == 100

        # 结果查询（N 区数据源）
        rows = client.get(f"/api/v1/backtest/results?strategy_id={sid}", headers=_auth(token)).json()["data"]
        assert rows and rows[0]["id"] == result["result_id"]
        assert rows[0]["win_rate"] is not None and rows[0]["metrics_json"]

        # 结果详情
        detail = client.get(f"/api/v1/backtest/results/{result['result_id']}", headers=_auth(token)).json()["data"]
        assert detail["task_id"] == task_id
        assert detail["metrics_json"]["total_trades"] >= 1
    finally:
        _cleanup_users(uname)


def test_backtest_no_kline_marks_failed(client: TestClient, monkeypatch):
    uname = _uname()
    try:
        _make_mocks(monkeypatch, bars=[])
        token = _register(client, uname)
        sid = _create_strategy(client, token)
        r = client.post("/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519"}, headers=_auth(token))
        task_id = r.json()["data"]["id"]

        with pytest.raises(backtest_service.BacktestFatalError):
            backtest_service.execute_backtest(task_id)
        # worker 任务层捕获 fatal 后标记 failed
        backtest_service.mark_task_failed(task_id, "标的无 K 线数据")
        task = client.get(f"/api/v1/backtest/tasks/{task_id}", headers=_auth(token)).json()["data"]
        assert task["status"] == "failed" and task["error"]
    finally:
        _cleanup_users(uname)


# ---- 鉴权与隔离 ----
def test_backtest_requires_auth(client: TestClient, monkeypatch):
    _make_mocks(monkeypatch)
    assert client.post("/api/v1/backtest", json={"strategy_id": 1, "symbol": "600519"}).status_code == 401
    assert client.get("/api/v1/backtest/tasks/1").status_code == 401


def test_backtest_ownership(client: TestClient, monkeypatch):
    u1, u2 = _uname(), _uname()
    try:
        _make_mocks(monkeypatch)
        t1 = _register(client, u1)
        t2 = _register(client, u2)
        sid = _create_strategy(client, t1)
        r = client.post("/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519"}, headers=_auth(t1))
        task_id = r.json()["data"]["id"]
        backtest_service.execute_backtest(task_id)

        # 他人查任务/结果 → 404（越权隔离）
        assert client.get(f"/api/v1/backtest/tasks/{task_id}", headers=_auth(t2)).status_code == 404
        assert client.get(f"/api/v1/backtest/results?strategy_id={sid}", headers=_auth(t2)).status_code == 404
        # 用他人策略发起回测 → 404
        r = client.post("/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519"}, headers=_auth(t2))
        assert r.status_code == 404
    finally:
        _cleanup_users(u1, u2)


def test_backtest_validation(client: TestClient, monkeypatch):
    uname = _uname()
    try:
        _make_mocks(monkeypatch)
        token = _register(client, uname)
        sid = _create_strategy(client, token)
        # 非法周期 → 422（pydantic pattern 校验）
        r = client.post("/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519", "period": "5m"}, headers=_auth(token))
        assert r.status_code == 422
        # 不存在的策略 → 404
        assert client.post("/api/v1/backtest", json={"strategy_id": 999999, "symbol": "600519"}, headers=_auth(token)).status_code == 404
    finally:
        _cleanup_users(uname)


def test_backtest_task_list(client: TestClient, monkeypatch):
    uname = _uname()
    try:
        _make_mocks(monkeypatch)
        token = _register(client, uname)
        sid = _create_strategy(client, token)
        client.post("/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519"}, headers=_auth(token))
        rows = client.get(f"/api/v1/backtest/tasks?strategy_id={sid}", headers=_auth(token)).json()["data"]
        assert len(rows) >= 1
    finally:
        _cleanup_users(uname)

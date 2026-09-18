"""G12 · P1-2c 任务幂等审计的回归测试（真实 DB + 真实子进程执行）。

Celery 是 **at-least-once** 语义：worker 被强杀后未 ack 的任务会被重投。因此每个任务都必须
能安全地重复执行。本文件覆盖审计中发现并修复的那一处不幂等 —— `run_backtest_task` 重复执行
会重复落库 `backtest_results`（用户会看到两条重复结果）。
"""

import types
import uuid

import pytest
from app.models.user import User
from app.repositories import backtest_repo, kline_repo
from app.services import backtest_quota, backtest_service
from app.utils.db import get_session
from app.utils.redis_client import get_redis_client
from fastapi.testclient import TestClient

_PREFIX = "test_g12_"

_SMA_STRATEGY = """
def initialize(context):
    pass

def on_bar(bar, context):
    n = 5
    closes = context.closes
    if len(closes) < n:
        return
    ma = sum(closes[-n:]) / n
    if bar["close"] > ma and context.pos == 0:
        context.buy()
    elif bar["close"] < ma and context.pos > 0:
        context.sell()
"""


def _fake_bars(n: int = 60) -> list[types.SimpleNamespace]:
    from datetime import UTC, datetime, timedelta

    out = []
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(n):
        c = round(10 + (i if i < 30 else 60 - i) * 0.3, 3)
        out.append(
            types.SimpleNamespace(
                ts=ts + timedelta(days=i), open=c, high=c + 0.1, low=c - 0.1, close=c, volume=1000, amount=c * 1000
            )
        )
    return out


def _cleanup(username: str) -> None:
    db = get_session()
    try:
        row = db.query(User).filter(User.username == username).first()
        if row:
            db.delete(row)
        db.commit()
    finally:
        db.close()


@pytest.fixture
def prepared(client: TestClient, monkeypatch):
    """建用户 + 策略 + 一个 queued 回测任务（Celery/K线/记忆均打桩，执行走真实子进程）。"""
    uname = f"{_PREFIX}{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(
        "app.worker.tasks.backtest_tasks.run_backtest_task",
        types.SimpleNamespace(delay=lambda task_id, quota_token=None: None),
    )
    monkeypatch.setattr(kline_repo, "get_bars", lambda db, period, symbol_id, start, end, limit=1000: _fake_bars())
    monkeypatch.setattr(backtest_service, "_save_backtest_memory", lambda *a, **k: None)
    get_redis_client().delete(backtest_quota.BACKTEST_QUEUE)
    try:
        reg = client.post(
            "/api/v1/auth/register",
            json={"username": uname, "password": "pass123456", "email": f"{uname}@test.local"},
        )
        assert reg.status_code == 200, reg.text
        token = reg.json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}
        sid = client.post(
            "/api/v1/strategies",
            json={"title": "G12 双均线", "description": "t", "code": _SMA_STRATEGY, "params": {}, "status": "active"},
            headers=headers,
        ).json()["data"]["id"]
        task_id = client.post(
            "/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519", "period": "1d"}, headers=headers
        ).json()["data"]["id"]
        yield task_id
    finally:
        get_redis_client().delete(backtest_quota.BACKTEST_QUEUE)
        _cleanup(uname)


def test_backtest_task_is_idempotent_on_redelivery(prepared):
    """同一 task_id 重复执行（Celery 重投）**不得**重复落库结果。

    审计发现：`execute_backtest` 每次执行都会 `create_result`，而 Celery 是 at-least-once ——
    worker 被强杀后任务会被重投，用户会看到两条一模一样的回测结果。修复：任务已 success 且
    结果存在时短路返回既有结果。
    """
    task_id = prepared

    first = backtest_service.execute_backtest(task_id)
    assert first.get("idempotent") is not True, "首次执行不应走幂等短路"
    first_result_id = first["result_id"]

    # 模拟 Celery 重投：同一个 task_id 再跑一次
    second = backtest_service.execute_backtest(task_id)

    assert second.get("idempotent") is True, "重复执行必须命中幂等短路"
    assert second["result_id"] == first_result_id, "应返回既有结果而非新建"

    db = get_session()
    try:
        rows = db.query(backtest_repo.BacktestResult).filter(backtest_repo.BacktestResult.task_id == task_id).all()
        assert len(rows) == 1, f"同一任务只应有一条结果，实际 {len(rows)} 条"
        task = backtest_repo.get_task(db, task_id)
        assert task.status == "success"
    finally:
        db.close()


def test_backtest_task_rerun_does_not_change_stored_result(prepared):
    """重复执行**不得改动已落库的结果**（不重算、不覆盖）。

    注：幂等路径返回的是 `result.metrics_json`（存储形态），首次执行返回的是
    `compute_metrics()` 的完整返回（含外层 win_rate 等字段）——两者**形状不同但同源**。
    这里断言的是真正的不变式：库里那条结果在重投前后逐字节一致。
    """
    task_id = prepared
    first = backtest_service.execute_backtest(task_id)

    db = get_session()
    try:
        before = backtest_repo.get_result(db, first["result_id"])
        snapshot = (before.metrics_json, before.equity_curve, before.trades)
    finally:
        db.close()

    second = backtest_service.execute_backtest(task_id)
    assert second["result_id"] == first["result_id"]

    db = get_session()
    try:
        after = backtest_repo.get_result(db, first["result_id"])
        assert after.metrics_json == snapshot[0]
        assert after.equity_curve == snapshot[1]
        assert after.trades == snapshot[2]
    finally:
        db.close()

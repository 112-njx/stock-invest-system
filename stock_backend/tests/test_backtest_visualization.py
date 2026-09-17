"""V0.3 泳道D G32（P1-11）：回测结果可视化数据链路测试。

覆盖：
1. 迁移 0013 两列存在（equity_curve/trades，JSONB 可空）
2. execute_backtest 落库含 equity_curve/trades，且 ts 已序列化为 ISO8601
3. 详情端点返回两字段；列表端点**不含**两字段（大字段裁剪）
4. 存量结果行（两列为 NULL）不报错，详情返回 null
5. 序列化口径：equity_curve 长度 == K 线根数；trades 的 side/reason 与引擎一致
"""

import types
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from app.backtest import metrics
from app.models.user import User
from app.repositories import backtest_repo, kline_repo
from app.services import backtest_service
from app.utils.db import engine, get_session
from fastapi.testclient import TestClient

_PREFIX = "test_btv_"

# 先买后卖：确保产生完整买卖回合（含买卖两侧流水）
_BUY_SELL_STRATEGY = """
def initialize(context):
    pass
def on_bar(bar, context):
    if context.bar_index == 2 and context.pos == 0:
        context.buy()
    elif context.bar_index == 6 and context.pos > 0:
        context.sell()
"""


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _register(client: TestClient, username: str) -> str:
    r = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "pass123456", "email": f"{username}@test.local"},
    )
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


def _fake_bars(n=12):
    """合成日K：单调上行，非一字板（high/low 留价差，避免被涨跌停判定拦截）。"""
    bars = []
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(n):
        c = round(10 + i * 0.2, 3)
        bars.append(
            types.SimpleNamespace(
                ts=ts + timedelta(days=i),
                open=round(c - 0.05, 3),
                high=round(c + 0.1, 3),
                low=round(c - 0.1, 3),
                close=c,
                volume=100000,
                amount=round(c * 100000, 2),
            )
        )
    return bars


def _make_mocks(monkeypatch, bars=None):
    monkeypatch.setattr(
        "app.worker.tasks.backtest_tasks.run_backtest_task",
        types.SimpleNamespace(delay=lambda task_id: None),
    )
    monkeypatch.setattr(
        kline_repo,
        "get_bars",
        lambda db, period, symbol_id, start, end, limit=1000: (bars if bars is not None else _fake_bars()),
    )
    monkeypatch.setattr(backtest_service, "_save_backtest_memory", lambda *a, **k: None)


def _create_strategy(client: TestClient, token: str) -> int:
    r = client.post(
        "/api/v1/strategies",
        json={
            "title": "G32 买卖点",
            "description": "固定 bar 买/卖",
            "code": _BUY_SELL_STRATEGY,
            "params": {},
            "status": "active",
        },
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _run_backtest(client: TestClient, token: str, sid: int) -> dict:
    r = client.post(
        "/api/v1/backtest",
        json={"strategy_id": sid, "symbol": "600519", "period": "1d"},
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    return backtest_service.execute_backtest(r.json()["data"]["id"])


# ---- 1. 迁移 ----
def test_migration_0013_columns_exist():
    """迁移 0013 已应用：两列为 jsonb 且可空。"""
    insp = sa.inspect(engine)
    cols = {c["name"]: c for c in insp.get_columns("backtest_results")}
    assert "equity_curve" in cols, "backtest_results 缺少 equity_curve 列（0013 未应用？）"
    assert "trades" in cols, "backtest_results 缺少 trades 列（0013 未应用？）"
    assert cols["equity_curve"]["nullable"] is True
    assert cols["trades"]["nullable"] is True
    assert "JSONB" in str(cols["equity_curve"]["type"]).upper()
    assert "JSONB" in str(cols["trades"]["type"]).upper()


# ---- 2/3/5. 落库 + 端点裁剪 + 口径 ----
def test_execute_backtest_persists_curve_and_trades(client: TestClient, monkeypatch):
    """回测执行后 equity_curve/trades 落库，且 ts 序列化为 ISO8601。"""
    uname = _uname()
    try:
        _make_mocks(monkeypatch)
        token = _register(client, uname)
        sid = _create_strategy(client, token)
        out = _run_backtest(client, token, sid)

        db = get_session()
        try:
            row = backtest_repo.get_result(db, out["result_id"])
            assert row is not None
            assert isinstance(row.equity_curve, list) and row.equity_curve, "equity_curve 未落库"
            assert isinstance(row.trades, list) and row.trades, "trades 未落库"
            # 序列化口径：ts 为 ISO8601 字符串
            assert isinstance(row.equity_curve[0]["ts"], str)
            assert isinstance(row.trades[0]["ts"], str)
            assert row.equity_curve[0]["ts"].startswith("2024-01-01")
            # 曲线点数 == K 线根数
            assert len(row.equity_curve) == len(_fake_bars())
            # 买卖两侧流水齐全，reason 为引擎口径
            sides = [t["side"] for t in row.trades]
            assert "buy" in sides and "sell" in sides
            assert {t["reason"] for t in row.trades} <= {"signal", "stop_loss", "take_profit"}
        finally:
            db.close()

        # 详情端点返回两字段
        detail = client.get(f"/api/v1/backtest/results/{out['result_id']}", headers=_auth(token)).json()["data"]
        assert isinstance(detail["equity_curve"], list) and len(detail["equity_curve"]) == len(_fake_bars())
        assert isinstance(detail["trades"], list) and detail["trades"]
        first_buy = next(t for t in detail["trades"] if t["side"] == "buy")
        assert first_buy["price"] > 0 and first_buy["shares"] > 0 and first_buy["fee"] >= 0
        assert set(first_buy) == {"ts", "side", "price", "shares", "amount", "fee", "reason", "realized_pnl"}
        assert first_buy["realized_pnl"] is None  # 买入笔无已实现盈亏
        # 卖出笔的已实现盈亏与 metrics._pair_trades（胜率同口径）一致
        assert all(t["realized_pnl"] is not None for t in detail["trades"] if t["side"] == "sell")

        # 列表端点裁剪：不含两字段
        rows = client.get(f"/api/v1/backtest/results?strategy_id={sid}", headers=_auth(token)).json()["data"]
        assert rows and rows[0]["id"] == out["result_id"]
        assert "equity_curve" not in rows[0], "列表端点不应返回 equity_curve"
        assert "trades" not in rows[0], "列表端点不应返回 trades"
        # 汇总字段仍在（向后兼容）
        assert "win_rate" in rows[0] and "metrics_json" in rows[0]
    finally:
        _cleanup_users(uname)


# ---- 4. 存量 NULL 行降级 ----
def test_legacy_null_columns_do_not_break(client: TestClient, monkeypatch):
    """存量结果行（0013 前生成，两列为 NULL）详情返回 null，不报错。"""
    uname = _uname()
    try:
        _make_mocks(monkeypatch)
        token = _register(client, uname)
        sid = _create_strategy(client, token)
        out = _run_backtest(client, token, sid)

        # 模拟存量行：手工把两列置 NULL
        db = get_session()
        try:
            row = backtest_repo.get_result(db, out["result_id"])
            row.equity_curve = None
            row.trades = None
            db.commit()
        finally:
            db.close()

        detail = client.get(f"/api/v1/backtest/results/{out['result_id']}", headers=_auth(token)).json()["data"]
        assert detail["equity_curve"] is None
        assert detail["trades"] is None
        # 汇总指标不受影响
        assert detail["metrics_json"]["total_trades"] >= 1

        rows = client.get(f"/api/v1/backtest/results?strategy_id={sid}", headers=_auth(token)).json()["data"]
        assert rows and rows[0]["id"] == out["result_id"]
    finally:
        _cleanup_users(uname)


def test_serialize_helpers_handle_empty_and_naive():
    """序列化辅助：空列表 → None；naive datetime 按 UTC 标注。"""
    assert backtest_service._serialize_curve(None) is None
    assert backtest_service._serialize_curve([]) is None
    assert backtest_service._serialize_trades(None) is None
    assert backtest_service._serialize_trades([]) is None

    naive = datetime(2024, 1, 2, 3, 4, 5)
    assert backtest_service._iso(naive) == "2024-01-02T03:04:05+00:00"
    assert backtest_service._iso(datetime(2024, 1, 2, tzinfo=UTC)) == "2024-01-02T00:00:00+00:00"
    assert backtest_service._iso(None) is None

    curve = backtest_service._serialize_curve(
        [{"ts": naive, "equity": 100.5, "cash": 50.25, "pos": 10, "price": 5.025}]
    )
    assert curve == [
        {"ts": "2024-01-02T03:04:05+00:00", "equity": 100.5, "cash": 50.25, "pos": 10, "price": 5.025}
    ]

    trades = backtest_service._serialize_trades(
        [{"ts": naive, "side": "sell", "price": 10.0, "shares": 100, "amount": 1000.0, "fee": 0.8}]
    )
    assert trades[0]["reason"] == "signal"  # 缺省补 signal
    assert trades[0]["side"] == "sell" and trades[0]["shares"] == 100
    assert trades[0]["realized_pnl"] == 0.0  # 无对应买入 → 无配对盈亏


def test_realized_pnl_matches_metrics_pairing():
    """已实现盈亏逐笔归集：卖出笔数一致，且总额 == metrics._pair_trades 的净盈亏之和。"""
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    # 两笔买入（分批）+ 两笔卖出（第二笔跨两个批次）→ 覆盖「一卖拆多段配对」
    raw = [
        {"ts": t0, "side": "buy", "price": 10.0, "shares": 100, "amount": 1000.0, "fee": 0.3, "reason": "signal"},
        {"ts": t0 + timedelta(days=1), "side": "buy", "price": 11.0, "shares": 100, "amount": 1100.0, "fee": 0.33, "reason": "signal"},
        {"ts": t0 + timedelta(days=2), "side": "sell", "price": 12.0, "shares": 100, "amount": 1200.0, "fee": 0.96, "reason": "signal"},
        {"ts": t0 + timedelta(days=3), "side": "sell", "price": 13.0, "shares": 100, "amount": 1300.0, "fee": 1.04, "reason": "take_profit"},
    ]
    out = backtest_service._serialize_trades(raw)
    assert [t["realized_pnl"] for t in out if t["side"] == "buy"] == [None, None]

    sell_pnls = [t["realized_pnl"] for t in out if t["side"] == "sell"]
    assert len(sell_pnls) == 2

    pairs = metrics._pair_trades(raw)
    assert len(pairs) == 2
    assert abs(sum(sell_pnls) - sum(p["net_pnl"] for p in pairs)) < 0.01
    # 逐笔对齐：第 1 笔卖配 10.0 批次（净盈利），第 2 笔卖配 11.0 批次
    assert sell_pnls[0] == round(pairs[0]["net_pnl"], 2)
    assert sell_pnls[1] == round(pairs[1]["net_pnl"], 2)
    # 净盈亏已扣费用：毛赚 (12-10)*100=200，净额必然更小
    assert sell_pnls[0] < 200

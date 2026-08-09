"""阶段四 4.1 回测引擎 + 4.2 指标计算 单元测试（合成 K 线，不依赖 DB/网络）。"""

from datetime import UTC, datetime, timedelta

import pytest
from app.backtest import metrics
from app.backtest.engine import BacktestConfig, BacktestEngine, BacktestError
from app.backtest.sandbox import SandboxError, compile_strategy


def make_bars(closes, opens=None, highs=None, lows=None, start=None, step_days=1):
    bars = []
    ts = start or datetime(2024, 1, 1, tzinfo=UTC)
    for i, c in enumerate(closes):
        o = opens[i] if opens else c
        h = highs[i] if highs else max(o, c)
        lo = lows[i] if lows else min(o, c)
        bars.append(
            {"ts": ts + timedelta(days=i * step_days), "open": o, "high": h, "low": lo, "close": c, "volume": 1000, "amount": float(c) * 1000}
        )
    return bars


# 简单双均线策略：收盘 > 均线持有，否则空仓
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


# ---- 4.1 沙箱 ----
def test_compile_strategy_ok():
    funcs = compile_strategy(_SMA_STRATEGY)
    assert callable(funcs["initialize"])
    assert callable(funcs["on_bar"])


def test_sandbox_rejects_import():
    with pytest.raises(SandboxError, match="import"):
        compile_strategy("import os\ndef on_bar(bar, c):\n    pass\n")


def test_sandbox_rejects_dangerous_builtins():
    for bad in [
        "def on_bar(bar, c):\n    open(\"x\", \"w\")\n",
        "def on_bar(bar, c):\n    eval(\"1\")\n",
        "def on_bar(bar, c):\n    __import__(\"os\")\n",
    ]:
        with pytest.raises(SandboxError):
            compile_strategy(bad)


def test_sandbox_rejects_missing_on_bar():
    with pytest.raises(SandboxError, match="on_bar"):
        compile_strategy("def initialize(context):\n    pass\n")


def test_sandbox_rejects_underscore_attr_access():
    """策略访问 __class__ 被受限守卫拦截（编译期）。"""
    with pytest.raises(SandboxError, match="invalid attribute"):
        compile_strategy("def on_bar(bar, c):\n    c.__class__\n    return 1\n")


# ---- 4.1 撮合 ----
def test_run_simple_strategy_produces_trades():
    # 先涨后跌：均线策略应产生买入再卖出
    closes = [10 + i * 0.5 for i in range(20)] + [20 - i * 0.5 for i in range(1, 21)]
    eng = BacktestEngine(config=BacktestConfig(initial_cash=100_000))
    out = eng.run(_SMA_STRATEGY, {"entry": {"fast": 5}}, make_bars(closes))
    assert out["trades"], "双均线策略应产生交易流水"
    assert out["equity_curve"]
    assert len(out["equity_curve"]) == 40
    sides = {t["side"] for t in out["trades"]}
    assert sides == {"buy", "sell"}


def test_t1_restriction():
    """T+1：当日买入当日不可卖，次日可卖。"""
    strategy = """
def on_bar(bar, context):
    if bar["close"] > 100:
        if context.pos == 0:
            context.buy(10)
        else:
            context.sell(10)  # 同一根 bar 内再尝试卖（T+1 应拦截）
    elif bar["close"] < 100 and context.pos > 0:
        context.sell(10)  # 次日
"""
    eng = BacktestEngine(config=BacktestConfig(initial_cash=100_000))
    bars = make_bars([101.0, 99.0, 99.0])
    out = eng.run(strategy, {}, bars)
    # 第一根 bar buy(10) 后同 bar sell 被 T+1 拦截；第二根 bar 才卖出
    assert len(out["trades"]) == 2
    assert out["trades"][0]["side"] == "buy"
    assert out["trades"][1]["side"] == "sell"


def test_auto_stop_loss():
    """自动止损：params.stop_loss.pct 触发，按触发价成交。"""
    strategy = """
def on_bar(bar, context):
    if context.pos == 0 and bar["close"] > 100:
        context.buy(100)
"""
    eng = BacktestEngine(config=BacktestConfig(initial_cash=100_000))
    # 买入价 101；bar1 低点 85 触发止损 101*0.9=90.9
    bars = make_bars([101.0, 90.0], highs=[101.0, 95.0], lows=[101.0, 85.0])
    out = eng.run(strategy, {"stop_loss": {"pct": 0.10}, "take_profit": {"pct": 0.20}}, bars)
    sells = [t for t in out["trades"] if t["side"] == "sell"]
    assert sells and sells[0]["reason"] == "stop_loss"
    assert sells[0]["price"] == pytest.approx(90.9, abs=0.01)


def test_fill_price_fee():
    """撮合价与费用：close 模式按收盘价成交，佣金 + 印花税计入。"""
    strategy = """
def initialize(context):
    pass
def on_bar(bar, context):
    if context.bar_index == 0:
        context.buy(100)
    elif context.bar_index == 1:
        context.sell(100)
"""
    eng = BacktestEngine(config=BacktestConfig(initial_cash=100_000, commission_rate=0.0003, stamp_duty_rate=0.0005))
    out = eng.run(strategy, {}, make_bars([10.0, 12.0]))
    buy, sell = out["trades"][0], out["trades"][1]
    assert buy["price"] == 10.0 and buy["fee"] == pytest.approx(10 * 100 * 0.0003)
    assert sell["price"] == 12.0 and sell["fee"] == pytest.approx(12 * 100 * (0.0003 + 0.0005))
    # 现金：100000 - 1000 - 0.3 + 1200 - 0.96
    assert out["equity_curve"][-1]["cash"] == pytest.approx(100000 - 1000 - 0.3 + 1200 - 0.96)


def test_time_budget_exceeded():
    """时间预算：策略正常但 bar 极多 + 预算极小 → 超时。"""
    strategy = "def on_bar(bar, context):\n    pass\n"
    eng = BacktestEngine(config=BacktestConfig(initial_cash=100_000, time_budget=0.0001))
    bars = make_bars([10.0 + i * 0.01 for i in range(5000)])
    from app.backtest.engine import BacktestTimeout

    with pytest.raises(BacktestTimeout):
        eng.run(strategy, {}, bars)


def test_invalid_strategy_code():
    eng = BacktestEngine()
    with pytest.raises(BacktestError):
        eng.run("def on_bar(bar, c):\n  x =\n", {}, make_bars([1.0, 2.0]))


# ---- 4.2 指标 ----
def test_metrics_known_case():
    trades = [
        {"side": "buy", "price": 10.0, "shares": 100, "ts": datetime(2024, 1, 1, tzinfo=UTC), "fee": 0.3},
        {"side": "sell", "price": 12.0, "shares": 100, "ts": datetime(2024, 1, 2, tzinfo=UTC), "fee": 0.96},  # 盈利 +200
        {"side": "buy", "price": 20.0, "shares": 100, "ts": datetime(2024, 2, 1, tzinfo=UTC), "fee": 0.6},
        {"side": "sell", "price": 18.0, "shares": 100, "ts": datetime(2024, 2, 2, tzinfo=UTC), "fee": 1.44},  # 亏损 -200
    ]
    equity = [
        {"ts": datetime(2024, 1, 1, tzinfo=UTC), "equity": 100_000},
        {"ts": datetime(2024, 1, 2, tzinfo=UTC), "equity": 100_200},
        {"ts": datetime(2024, 2, 1, tzinfo=UTC), "equity": 99_000},
        {"ts": datetime(2024, 2, 2, tzinfo=UTC), "equity": 98_800},
    ]
    m = metrics.compute_metrics(trades, equity, 100_000, equity[0]["ts"], equity[-1]["ts"], period="1d")
    assert m["win_rate"] == pytest.approx(0.5)
    assert m["profit_loss_ratio"] == pytest.approx(1.0)
    assert m["total_buys"] == 2 and m["total_sells"] == 2
    assert m["max_drawdown"] == pytest.approx((100_200 - 98_800) / 100_200, abs=0.001)
    assert m["metrics_json"]["total_trades"] == 2
    assert m["metrics_json"]["best_trade"] == pytest.approx(200.0)
    assert m["metrics_json"]["worst_trade"] == pytest.approx(-200.0)


def test_metrics_no_trades():
    m = metrics.compute_metrics([], [{"equity": 100_000}], 100_000, None, None, "1d")
    assert m["win_rate"] is None
    assert m["profit_loss_ratio"] is None
    assert m["sharpe"] is None
    assert m["total_buys"] == 0


def test_metrics_drawdown_and_return():
    equity = [
        {"ts": datetime(2024, 1, 1, tzinfo=UTC), "equity": 100_000},
        {"ts": datetime(2024, 1, 2, tzinfo=UTC), "equity": 120_000},
        {"ts": datetime(2024, 1, 3, tzinfo=UTC), "equity": 100_000},  # 从 120k 回撤 20k
        {"ts": datetime(2024, 1, 4, tzinfo=UTC), "equity": 110_000},
    ]
    m = metrics.compute_metrics([], equity, 100_000, equity[0]["ts"], equity[-1]["ts"], "1d")
    assert m["max_drawdown"] == pytest.approx(20000 / 120000, abs=0.001)
    assert m["annual_return"] is not None and m["annual_return"] > 0


def test_metrics_sharpe():
    """单调上涨 → 年化夏普为正。"""
    equity = [{"ts": datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i), "equity": 100_000 * (1 + i * 0.001)} for i in range(252)]
    m = metrics.compute_metrics([], equity, 100_000, equity[0]["ts"], equity[-1]["ts"], "1d")
    assert m["sharpe"] is not None and m["sharpe"] > 0

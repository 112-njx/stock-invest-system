"""P0-10 回测正确性回归测试（G06 测试先行 → G20 修复后锁定）。

本文件在 G06 阶段以「修复前基线 + 修复后目标（xfail）」形式落地，
G20 修复完成后转为纯目标断言（本版本），锁定修复后的净盈亏/回合/期末结算口径。

覆盖 6 类缺陷修复：
1. 净盈亏配对（扣买卖费用）
2. 期末未平仓浮动结算
3. 完整交易回合口径（FIFO 仅用于成本分摊）
4. 平手（draw）单列不并入亏损
5. 统一成本法（FIFO 用于止损触发价）
6. 撮合现实性（滑点/成交量/涨跌停/同 bar 禁止再入）
"""

from datetime import UTC, datetime, timedelta

import pytest
from app.backtest import metrics
from app.backtest.engine import BacktestConfig, BacktestEngine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bars(specs: list[dict]) -> list[dict]:
    """构造确定性 K 线序列。

    specs: [{"c": close}, ...] 或完整 {"o","h","l","c","v","a"}
    默认 high/low 加微小价差，避免 o=h=l=c（一字板）被涨跌停检查拦截；
    显式传 o/h/l/c 全等时即构造一字板（用于涨跌停场景）。
    """
    result = []
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    for i, s in enumerate(specs):
        c = s["c"]
        o = s.get("o", c)
        h = s.get("h", max(o, c) * 1.001)
        lo = s.get("l", min(o, c) * 0.999)
        v = s.get("v", 100_000)
        a = s.get("a", float(c) * v)
        result.append({
            "ts": ts + timedelta(days=i),
            "open": o, "high": h, "low": lo, "close": c,
            "volume": v, "amount": a,
        })
    return result


def _config(**kw) -> BacktestConfig:
    defaults = dict(
        initial_cash=100_000,
        commission_rate=0.001,      # 千分之一（放大费用便于验证）
        stamp_duty_rate=0.0005,     # 万分之五（卖出单边）
        fill_on="close",
        slippage_pct=0.0,
        time_budget=10.0,
    )
    defaults.update(kw)
    return BacktestConfig(**defaults)


def _run(code: str, params: dict | None, bars: list[dict], **cfg_kw) -> dict:
    """运行策略，返回 engine output dict。"""
    eng = BacktestEngine(config=_config(**cfg_kw))
    return eng.run(code, params or {}, bars)


def _metrics(out: dict) -> dict:
    """按服务层口径计算指标（含期末持仓结算）。"""
    return metrics.compute_metrics(
        out["trades"], out["equity_curve"], out["initial_cash"],
        out["start_ts"], out["end_ts"], "1d",
        open_position=out.get("open_position"),
    )


# ---------------------------------------------------------------------------
# 策略代码
# ---------------------------------------------------------------------------

# 买入后下一根 bar 卖出（确定性一买一卖）
_BUY_THEN_SELL = """
def on_bar(bar, context):
    if context.bar_index == 0:
        context.buy(100)
    elif context.bar_index == 1:
        context.sell(100)
"""

# 两根 bar 分别买入，第三根 bar 一次性全部卖出
_SPLIT_BUY = """
def on_bar(bar, context):
    if context.bar_index == 0:
        context.buy(100)
    elif context.bar_index == 1:
        context.buy(100)
    elif context.bar_index == 2:
        context.sell()
"""

# 买入后一直持有（不卖出）
_HOLD_ONLY = """
def on_bar(bar, context):
    if context.bar_index == 0:
        context.buy(100)
"""

# 第一根 bar 买入，第二根 bar 以买入价卖出（平手）
_EVEN_MONEY = """
def on_bar(bar, context):
    if context.bar_index == 0:
        context.buy(100)
    elif context.bar_index == 1:
        context.sell(100)
"""

# 涨停场景：bar1 涨停时尝试买入，bar2 卖出
_LIMIT_UP_STRATEGY = """
def on_bar(bar, context):
    if context.bar_index == 1 and context.pos == 0:
        context.buy()
    elif context.bar_index == 2 and context.pos > 0:
        context.sell()
"""

# 止损后尝试再买入（验证同 bar 禁止再入）
_STOPLOSS_THEN_BUY = """
def on_bar(bar, context):
    if context.bar_index == 0:
        context.buy(100)
    elif context.bar_index == 1:
        context.buy(100)
    elif context.bar_index == 2:
        if context.pos == 0:
            context.buy(100)
"""

# 微利交易（毛赚净亏）
_STRATEGY_MICRO_PROFIT = """
def on_bar(bar, context):
    if context.bar_index == 0:
        context.buy(100)
    elif context.bar_index == 1:
        context.sell(100)
"""

# 大额买入（验证成交量限制）
_STRATEGY_BULK_BUY = """
def on_bar(bar, context):
    if context.bar_index == 0:
        context.buy(10000)
    elif context.bar_index == 1:
        context.sell()
"""


# ===========================================================================
# 场景 1：净盈亏配对 — 配对 PnL 扣除买卖费用
# ===========================================================================
# Buy 100@10.0, Sell 100@12.0；佣金 0.1%，印花税 0.05%
#   毛 PnL = 200
#   买入佣金 = 10*100*0.001 = 1.0
#   卖出佣金 = 12*100*0.001 = 1.2，印花税 = 12*100*0.0005 = 0.6
#   净 PnL = 200 - 1.0 - 1.2 - 0.6 = 197.2

class TestNetPnlPairing:
    bars = _bars([{"c": 10.0}, {"c": 12.0}])

    def test_pair_net_pnl_deducts_fees(self):
        """配对净 PnL 扣除买入佣金 + 卖出佣金 + 印花税。"""
        out = _run(_BUY_THEN_SELL, {}, self.bars)
        pairs = metrics._pair_trades(out["trades"])
        assert len(pairs) == 1
        assert pairs[0]["pnl"] == pytest.approx(200.0)        # 毛
        assert pairs[0]["net_pnl"] == pytest.approx(197.2)    # 净

    def test_win_rate_and_best_use_net(self):
        """win_rate/best_trade/worst_trade 按净盈亏。"""
        out = _run(_BUY_THEN_SELL, {}, self.bars)
        m = _metrics(out)
        assert m["win_rate"] == pytest.approx(1.0)
        assert m["metrics_json"]["total_trades"] == 1
        assert m["metrics_json"]["best_trade"] == pytest.approx(197.2)
        assert m["metrics_json"]["worst_trade"] == pytest.approx(197.2)

    def test_total_return_reflects_fees(self):
        """总收益率反映实际现金变化（含费用）。"""
        out = _run(_BUY_THEN_SELL, {}, self.bars)
        m = _metrics(out)
        # 现金 = 100000-1001+1197.6 = 100196.6 → 0.1966%
        assert m["metrics_json"]["total_return"] == pytest.approx(0.001966, abs=1e-5)


# ===========================================================================
# 场景 2：完整交易回合口径 — 一次卖单配多段买单算一笔
# ===========================================================================
# Buy 100@10.0, Buy 100@11.0, Sell 200@12.0
#   FIFO 配对 2 段（成本分摊），但属于 1 个完整买→卖回合

class TestRoundTripCounting:
    bars = _bars([{"c": 10.0}, {"c": 11.0}, {"c": 12.0}])

    def test_fifo_segments_still_two(self):
        """FIFO 仍按成本分摊拆段（用于费用/成本核算）。"""
        out = _run(_SPLIT_BUY, {}, self.bars)
        pairs = metrics._pair_trades(out["trades"])
        assert len(pairs) == 2
        assert pairs[0]["net_pnl"] == pytest.approx(197.2)  # (12-10)*100 - 费用
        assert pairs[1]["net_pnl"] == pytest.approx(97.1)   # (12-11)*100 - 费用

    def test_total_trades_is_round_count(self):
        """total_trades 按完整回合计数（非 FIFO 段数）。"""
        out = _run(_SPLIT_BUY, {}, self.bars)
        m = _metrics(out)
        assert m["metrics_json"]["total_trades"] == 1
        assert m["win_rate"] == pytest.approx(1.0)

    def test_round_close_flag(self):
        """round_close 标记回合闭合位置（仅最后一段为 True）。"""
        out = _run(_SPLIT_BUY, {}, self.bars)
        pairs = metrics._pair_trades(out["trades"])
        assert pairs[0]["round_close"] is False
        assert pairs[1]["round_close"] is True


# ===========================================================================
# 场景 3：期末未平仓浮动结算
# ===========================================================================
# Buy 100@10.0，持有至期末（最后 bar close=15.0）
#   浮动盈亏 = (15.0 - 10.0) * 100 = 500

class TestEndOfPeriodSettlement:
    bars = _bars([{"c": 10.0}, {"c": 12.0}, {"c": 15.0}])

    def test_open_position_reported(self):
        """引擎输出期末未平仓信息。"""
        out = _run(_HOLD_ONLY, {}, self.bars)
        op = out["open_position"]
        assert op is not None
        assert op["shares"] == 100
        assert op["fifo_cost"] == pytest.approx(10.0)
        assert op["last_close"] == pytest.approx(15.0)

    def test_unrealized_pnl_settled(self):
        """期末持仓按最后收盘价浮动结算，metrics_json 单列。"""
        out = _run(_HOLD_ONLY, {}, self.bars)
        m = _metrics(out)
        mj = m["metrics_json"]
        assert mj["unrealized_count"] == 1
        assert mj["unrealized_pnl"] == pytest.approx(500.0)

    def test_no_realized_round(self):
        """未平仓不产生已实现回合（胜率口径区分已实现/未实现）。"""
        out = _run(_HOLD_ONLY, {}, self.bars)
        m = _metrics(out)
        assert m["metrics_json"]["total_trades"] == 0
        assert m["win_rate"] is None
        assert m["total_buys"] == 1 and m["total_sells"] == 0


# ===========================================================================
# 场景 4：平手交易单列 draw，不并入亏损
# ===========================================================================
# Buy 100@10.0, Sell 100@10.0（毛 PnL = 0）

class TestDrawClassification:
    bars = _bars([{"c": 10.0}, {"c": 10.0}])

    def test_gross_zero_is_draw(self):
        """毛盈亏为 0 → draw，不计入 win/loss。"""
        out = _run(_EVEN_MONEY, {}, self.bars)
        pairs = metrics._pair_trades(out["trades"])
        assert pairs[0]["pnl"] == pytest.approx(0.0)
        assert pairs[0]["net_pnl"] == pytest.approx(-2.5)  # 费用 1.0+1.0+0.5

    def test_draw_counted_separately(self):
        """draws 单列，win_rate 分母排除平手。"""
        out = _run(_EVEN_MONEY, {}, self.bars)
        m = _metrics(out)
        assert m["metrics_json"]["draws"] == 1
        # 无 win/loss 交易 → win_rate 无意义
        assert m["win_rate"] is None
        assert m["metrics_json"]["total_trades"] == 1


# ===========================================================================
# 场景 5：撮合现实性 — 涨停不买入
# ===========================================================================
# bar1 一字板涨停（o=h=l=c=10.8）→ 拒绝买入

class TestLimitUpNoBuy:
    bars = _bars([
        {"c": 10.0},
        {"o": 10.8, "h": 10.8, "l": 10.8, "c": 10.8},  # 一字涨停
        {"c": 11.0},
    ])

    def test_no_buy_at_limit_up(self):
        """触及涨停拒绝买入。"""
        out = _run(_LIMIT_UP_STRATEGY, {}, self.bars)
        buys = [t for t in out["trades"] if t["side"] == "buy"]
        assert len(buys) == 0

    def test_no_trades_at_all(self):
        """涨停无法建仓 → 后续也无卖出，权益不变。"""
        out = _run(_LIMIT_UP_STRATEGY, {}, self.bars)
        assert out["trades"] == []
        assert out["equity_curve"][-1]["equity"] == pytest.approx(100_000.0)


# ===========================================================================
# 场景 5b：撮合现实性 — 跌停不卖出
# ===========================================================================
# bar1 一字板跌停（o=h=l=c=9.0）→ 拒绝卖出（含自动止损）

class TestLimitDownNoSell:
    bars = _bars([
        {"c": 10.0},
        {"o": 9.0, "h": 9.0, "l": 9.0, "c": 9.0},  # 一字跌停
        {"c": 8.5},
    ])
    params = {"stop_loss": {"pct": 0.10}}

    def test_no_sell_on_limit_down_bar(self):
        """跌停当日拒绝卖出（止损触发也被拒）。"""
        out = _run(_BUY_THEN_SELL, self.params, self.bars)
        bar1_ts = self.bars[1]["ts"]
        bar1_sells = [t for t in out["trades"] if t["side"] == "sell" and t["ts"] == bar1_ts]
        assert len(bar1_sells) == 0

    def test_position_retained_after_limit_down(self):
        """跌停未卖出 → 持仓保留至下一根 bar 才平仓。"""
        out = _run(_BUY_THEN_SELL, self.params, self.bars)
        sells = [t for t in out["trades"] if t["side"] == "sell"]
        assert len(sells) == 1
        assert sells[0]["ts"] == self.bars[2]["ts"]  # 跌停次根 bar 才成交


# ===========================================================================
# 场景 6：同 bar 自动止损后禁止再开同向仓
# ===========================================================================
# bar0 buy 100@10.0, bar1 buy 100@11.0（FIFO 成本 10.0）
# bar2 h=12.0 l=9.0 c=10.0：止损价 = 10.0*0.9 = 9.0，low=9.0 触发
#   止损卖出 200@9.0 后，on_bar 见 pos==0 尝试再买 → 应被拒绝

class TestSameBarNoReentry:
    bars = _bars([
        {"c": 10.0},
        {"c": 11.0},
        {"o": 10.0, "h": 12.0, "l": 9.0, "c": 10.0},
    ])
    params = {"stop_loss": {"pct": 0.10}}

    def test_stoploss_fires_with_fifo_cost(self):
        """统一成本法：止损触发价基于 FIFO 首批成本 10.0 → 9.0。"""
        out = _run(_STOPLOSS_THEN_BUY, self.params, self.bars)
        sells = [t for t in out["trades"] if t["side"] == "sell"]
        assert len(sells) == 1
        assert sells[0]["reason"] == "stop_loss"
        assert sells[0]["price"] == pytest.approx(9.0)
        assert sells[0]["shares"] == 200

    def test_no_reentry_after_stoploss(self):
        """同 bar 止损平仓后禁止再开同向仓。"""
        out = _run(_STOPLOSS_THEN_BUY, self.params, self.bars)
        buys = [t for t in out["trades"] if t["side"] == "buy"]
        # 仅 bar0 + bar1 两次买入；bar2 止损后的再买被拒
        assert len(buys) == 2
        assert all(t["ts"] != self.bars[2]["ts"] for t in buys)


# ===========================================================================
# 场景 7：微利交易毛赚净亏 → 判定为 loss
# ===========================================================================
# Buy 100@10.0, Sell 100@10.01；毛 PnL=+1.0，净 PnL=-1.5015

class TestMicroProfitNetLoss:
    bars = _bars([{"c": 10.0}, {"c": 10.01}])

    def test_net_pnl_negative(self):
        """毛赚但净亏：净 PnL 为负。"""
        out = _run(_STRATEGY_MICRO_PROFIT, {}, self.bars)
        pairs = metrics._pair_trades(out["trades"])
        assert pairs[0]["pnl"] == pytest.approx(1.0, abs=0.01)
        assert pairs[0]["net_pnl"] == pytest.approx(-1.5015, abs=0.01)

    def test_win_rate_zero(self):
        """毛赚净亏 → 判定为 loss，胜率 0。"""
        out = _run(_STRATEGY_MICRO_PROFIT, {}, self.bars)
        m = _metrics(out)
        assert m["win_rate"] == pytest.approx(0.0)
        assert m["metrics_json"]["worst_trade"] < 0


# ===========================================================================
# 场景 8：撮合现实性 — 滑点
# ===========================================================================

class TestSlippage:
    bars = _bars([{"c": 10.0}, {"c": 12.0}])

    def test_slippage_affects_fill_price(self):
        """滑点：买入价上浮、卖出价下浮。"""
        out = _run(_BUY_THEN_SELL, {}, self.bars, slippage_pct=0.01)
        buy, sell = out["trades"][0], out["trades"][1]
        assert buy["price"] == pytest.approx(10.0 * 1.01, abs=0.01)
        assert sell["price"] == pytest.approx(12.0 * 0.99, abs=0.01)

    def test_no_slippage_by_default(self):
        """默认无滑点：按收盘价成交。"""
        out = _run(_BUY_THEN_SELL, {}, self.bars)
        assert out["trades"][0]["price"] == pytest.approx(10.0)


# ===========================================================================
# 场景 9：撮合现实性 — 成交量限制
# ===========================================================================

class TestVolumeCap:
    bars = _bars([{"c": 10.0, "v": 100}, {"c": 12.0, "v": 100}])

    def test_volume_cap_limits_shares(self):
        """单笔成交不超过 bar.volume × max_volume_pct。"""
        out = _run(_STRATEGY_BULK_BUY, {}, self.bars, max_volume_pct=0.1)
        buys = [t for t in out["trades"] if t["side"] == "buy"]
        assert len(buys) == 1
        assert buys[0]["shares"] == 10  # 100 * 0.1

    def test_no_cap_by_default(self):
        """默认 max_volume_pct=1.0：仅受资金约束。"""
        out = _run(_STRATEGY_BULK_BUY, {}, self.bars)
        buys = [t for t in out["trades"] if t["side"] == "buy"]
        assert len(buys) == 1
        # 资金 100000，价格 10，佣金 0.1% → 可买约 9990 股
        assert buys[0]["shares"] > 100

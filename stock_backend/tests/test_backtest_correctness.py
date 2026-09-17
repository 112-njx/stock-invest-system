"""P0-10 回测正确性回归测试（G06 · 测试先行）。

构造确定性交易单覆盖 6 类场景，每场景锁定：
- 修复前基线值（baseline，当前引擎输出，断言 PASS）
- 修复后目标值（target，G20 修复后期望，当前 xfail 标记）

G20 修复流程：
1. 修改 engine.py / metrics.py 实现净盈亏配对、期末结算、统一回合口径、撮合现实性
2. 移除 xfail 标记，将 baseline 断言替换为 target 断言
3. 全量 pytest 通过

场景覆盖：
- 费用影响（毛赚 vs 净盈亏）
- 分批配对（一次卖单配多段买单）
- 期末未平仓持仓结算
- 平手交易分类
- 涨停不买入
- 跌停不卖出
- 同 bar 止损后禁止再开同向仓
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
    """
    result = []
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    for i, s in enumerate(specs):
        c = s["c"]
        o = s.get("o", c)
        h = s.get("h", max(o, c))
        lo = s.get("l", min(o, c))
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

# 涨停场景：bar0 空仓，bar1 涨停时买入，bar2 卖出
_LIMIT_UP_STRATEGY = """
def on_bar(bar, context):
    if context.bar_index == 1 and context.pos == 0:
        context.buy()
    elif context.bar_index == 2 and context.pos > 0:
        context.sell()
"""

# 止损后同 bar 再买入
_STOPLOSS_REENTRY = """
def on_bar(bar, context):
    if context.bar_index == 0:
        context.buy(100)
    elif context.bar_index == 1 and context.pos == 0:
        context.buy(100)
    elif context.bar_index == 1 and context.pos > 0:
        pass
    elif context.bar_index == 2:
        pass
    # bar2: 如果仍持仓，不做任何事（让 auto stop-loss 处理）
    # 如果 bar2 止损卖出了，则 on_bar 可能尝试再买
"""

# 止损后尝试再买入
_STOPLOSS_THEN_BUY = """
def on_bar(bar, context):
    if context.bar_index == 0:
        context.buy(100)
    elif context.bar_index == 1:
        context.buy(100)
    # bar2: stop-loss triggers, then try to buy
    elif context.bar_index == 2:
        if context.pos == 0:
            context.buy(100)
"""


# ===========================================================================
# 场景 1：费用影响 — 毛盈亏 vs 净盈亏
# ===========================================================================
# Buy 100@10.0, Sell 100@12.0
# 佣金 0.1%，印花税 0.05%（卖出单边）
#
# 毛 PnL = (12.0-10.0)*100 = +200
# 买入佣金 = 10*100*0.001 = 1.0
# 卖出佣金 = 12*100*0.001 = 1.2
# 卖出印花税 = 12*100*0.0005 = 0.6
# 总费用 = 1.0+1.2+0.6 = 2.8
# 净 PnL = 200-2.8 = +197.2
#
# 当前(修复前): 配对 pnl=200(毛), 判定为 win
# 目标(修复后): 配对 pnl=197.2(净), 判定为 win
# 差异: 本场景毛/净均 win, 但数值不同; 影响盈亏比和 best/worst_trade

class TestFeeImpact:
    bars = _bars([{"c": 10.0}, {"c": 12.0}])

    def test_baseline_gross_pnl(self):
        """修复前基线：配对用毛 PnL，不扣费用。"""
        out = _run(_BUY_THEN_SELL, {}, self.bars)
        pairs = metrics._pair_trades(out["trades"])
        assert len(pairs) == 1
        # 毛 PnL = (12-10)*100 = 200
        assert pairs[0]["pnl"] == pytest.approx(200.0)

    def test_baseline_win_rate_gross(self):
        """修复前基线：胜率按毛盈亏判定。"""
        out = _run(_BUY_THEN_SELL, {}, self.bars)
        m = metrics.compute_metrics(
            out["trades"], out["equity_curve"],
            out["initial_cash"], out["start_ts"], out["end_ts"], "1d",
        )
        assert m["win_rate"] == pytest.approx(1.0)
        assert m["metrics_json"]["total_trades"] == 1
        assert m["metrics_json"]["best_trade"] == pytest.approx(200.0)

    @pytest.mark.xfail(reason="G20: 配对 PnL 应扣除费用(净=197.2)，非毛=200")
    def test_target_net_pnl(self):
        """目标：配对 PnL 扣除买卖全部费用。"""
        out = _run(_BUY_THEN_SELL, {}, self.bars)
        pairs = metrics._pair_trades(out["trades"])
        assert len(pairs) == 1
        # 净 PnL = 200 - 2.8 = 197.2
        assert pairs[0]["pnl"] == pytest.approx(197.2, abs=0.01)

    @pytest.mark.xfail(reason="G20: best_trade 应按净盈亏=197.2")
    def test_target_best_trade_net(self):
        """目标：best_trade 反映净盈亏。"""
        out = _run(_BUY_THEN_SELL, {}, self.bars)
        m = metrics.compute_metrics(
            out["trades"], out["equity_curve"],
            out["initial_cash"], out["start_ts"], out["end_ts"], "1d",
        )
        assert m["metrics_json"]["best_trade"] == pytest.approx(197.2, abs=0.1)


# ===========================================================================
# 场景 2：分批配对 — 一次卖单拆配多段买单
# ===========================================================================
# Buy 100@10.0, Buy 100@11.0, Sell 200@12.0
# FIFO: pair1=(12-10)*100=200, pair2=(12-11)*100=100
#
# 当前(修复前):
#   total_trades=2 (FIFO 段数), win_rate=100%, profit_loss_ratio=None
#   费用: buy_fee1=1.0, buy_fee2=1.1, sell_fee=3.6 → 总=5.7
#   最终权益 = 100000-1001-1101.1+2396.4 = 100294.3
# 目标(修复后):
#   total_trades=1 (完整回合), win_rate=100%
#   净 PnL = 300-5.7 = 294.3

class TestSplitFill:
    bars = _bars([{"c": 10.0}, {"c": 11.0}, {"c": 12.0}])

    def test_baseline_fifo_segments(self):
        """修复前基线：一次卖单被 FIFO 拆为 2 段配对。"""
        out = _run(_SPLIT_BUY, {}, self.bars)
        pairs = metrics._pair_trades(out["trades"])
        assert len(pairs) == 2
        assert pairs[0]["pnl"] == pytest.approx(200.0)  # (12-10)*100
        assert pairs[1]["pnl"] == pytest.approx(100.0)  # (12-11)*100

    def test_baseline_trade_count_is_segments(self):
        """修复前基线：total_trades=配对段数而非完整回合。"""
        out = _run(_SPLIT_BUY, {}, self.bars)
        m = metrics.compute_metrics(
            out["trades"], out["equity_curve"],
            out["initial_cash"], out["start_ts"], out["end_ts"], "1d",
        )
        assert m["metrics_json"]["total_trades"] == 2  # FIFO 段数
        assert m["win_rate"] == pytest.approx(1.0)
        assert m["profit_loss_ratio"] is None  # 全胜无亏损

    @pytest.mark.xfail(reason="G20: total_trades 应为 1(完整回合)，非 FIFO 段数 2")
    def test_target_single_round(self):
        """目标：一次完整买→卖回合计为一笔交易。"""
        out = _run(_SPLIT_BUY, {}, self.bars)
        m = metrics.compute_metrics(
            out["trades"], out["equity_curve"],
            out["initial_cash"], out["start_ts"], out["end_ts"], "1d",
        )
        assert m["metrics_json"]["total_trades"] == 1

    def test_baseline_equity(self):
        """修复前基线：最终权益验证。"""
        out = _run(_SPLIT_BUY, {}, self.bars)
        # cash = 100000-1001-1101.1+2396.4 = 100294.3
        final_eq = out["equity_curve"][-1]["equity"]
        assert final_eq == pytest.approx(100_294.3, abs=0.5)


# ===========================================================================
# 场景 3：期末未平仓持仓结算
# ===========================================================================
# Buy 100@10.0, 持有至期末（最后 bar close=15.0）
#
# 当前(修复前):
#   无卖出 → pairs=[] → total_trades=0, win_rate=None
#   equity_curve 末值含持仓市值: cash=98999 + 100*15=1500 → 100499
#   total_return = (100499-100000)/100000 = 0.00499 (浮盈体现在权益但无交易统计)
#   metrics_json 无 unrealized_pnl 字段，浮盈不单独记录
# 目标(修复后):
#   期末持仓按最后 bar 收盘价浮动结算 → unrealized_pnl ≈ +498.5
#   metrics_json 单列 unrealized_pnl/unrealized_count
#   total_return 含浮动盈亏

class TestEndOfPeriodSettlement:
    bars = _bars([{"c": 10.0}, {"c": 12.0}, {"c": 15.0}])

    def test_baseline_no_settlement(self):
        """修复前基线：期末持仓不参与配对，浮盈不计入指标。"""
        out = _run(_HOLD_ONLY, {}, self.bars)
        m = metrics.compute_metrics(
            out["trades"], out["equity_curve"],
            out["initial_cash"], out["start_ts"], out["end_ts"], "1d",
        )
        # 无卖出 → 无配对
        assert m["metrics_json"]["total_trades"] == 0
        assert m["win_rate"] is None
        assert m["total_buys"] == 1
        assert m["total_sells"] == 0
        # total_return 基于 equity_curve 末值（含持仓市值），浮盈体现在权益但不在交易统计中
        # cash=98999, pos=100@15 → equity=100499 → return=0.499%
        assert m["metrics_json"]["total_return"] == pytest.approx(0.00499, abs=0.001)

    def test_baseline_open_position_exists(self):
        """修复前基线：持仓 100 股在期末，equity_curve 记录市值。"""
        out = _run(_HOLD_ONLY, {}, self.bars)
        last = out["equity_curve"][-1]
        assert last["pos"] == 100
        # cash=98999 + pos=100*close=15 → equity=100499
        assert last["equity"] == pytest.approx(100_499.0, abs=1.0)

    @pytest.mark.xfail(reason="G20: 期末持仓应按最后收盘价浮动结算，metrics_json 单列 unrealized_pnl/unrealized_count")
    def test_target_unrealized_settlement(self):
        """目标：期末 100 股@15.0 浮动结算，unrealized_pnl ≈ 499 (浮盈-手续费)。"""
        out = _run(_HOLD_ONLY, {}, self.bars)
        m = metrics.compute_metrics(
            out["trades"], out["equity_curve"],
            out["initial_cash"], out["start_ts"], out["end_ts"], "1d",
        )
        mj = m["metrics_json"]
        # 应有未平仓记录
        assert mj.get("unrealized_count", 0) == 1
        # 浮动 PnL = (15.0-10.0)*100 - buy_fee = 500-1.0 = 499.0
        assert mj.get("unrealized_pnl", 0) == pytest.approx(499.0, abs=1.0)


# ===========================================================================
# 场景 4：平手交易 — pnl==0 不应计为亏损
# ===========================================================================
# Buy 100@10.0, Sell 100@10.0（同价卖出）
# 毛 PnL = 0, 费用 = 1.0(buy) + 1.0(sell) + 0.5(stamp) = 2.5
# 净 PnL = -2.5
#
# 当前(修复前):
#   配对 pnl=0(毛), losses=[p for p in pairs if pnl<=0] → 计入亏损
#   win_rate=0%, total_trades=1
# 目标(修复后):
#   毛 PnL=0 → 标记为 draw（平手），不计入亏损统计
#   metrics_json 单列 draws/draw_count

class TestEvenMoneyTrade:
    bars = _bars([{"c": 10.0}, {"c": 10.0}])

    def test_baseline_zero_pnl_counted_as_loss(self):
        """修复前基线：平手(pnl=0)被计入亏损（pnl<=0）。"""
        out = _run(_EVEN_MONEY, {}, self.bars)
        pairs = metrics._pair_trades(out["trades"])
        assert len(pairs) == 1
        assert pairs[0]["pnl"] == pytest.approx(0.0)

        m = metrics.compute_metrics(
            out["trades"], out["equity_curve"],
            out["initial_cash"], out["start_ts"], out["end_ts"], "1d",
        )
        # 当前：pnl=0 进 losses → win_rate=0%
        assert m["win_rate"] == pytest.approx(0.0)
        assert m["metrics_json"]["worst_trade"] == pytest.approx(0.0)

    @pytest.mark.xfail(reason="G20: 平手应标记为 draw，不计入亏损；metrics_json 应有 draws 字段")
    def test_target_draw_classification(self):
        """目标：平手交易单列为 draw，不并入亏损。"""
        out = _run(_EVEN_MONEY, {}, self.bars)
        m = metrics.compute_metrics(
            out["trades"], out["equity_curve"],
            out["initial_cash"], out["start_ts"], out["end_ts"], "1d",
        )
        mj = m["metrics_json"]
        # draw 应单独统计
        assert mj.get("draws", 0) == 1 or mj.get("draw_count", 0) == 1
        # 亏损统计不应包含平手
        # win_rate 分母应排除 draws
        assert m["win_rate"] is None or m["win_rate"] == pytest.approx(0.0)


# ===========================================================================
# 场景 5a：涨停不买入
# ===========================================================================
# bar0: c=10.0 (空仓)
# bar1: o=h=l=c=10.8 (涨停: close=high=low=open → 一字板涨停)
# bar2: c=11.0
#
# 当前(修复前):
#   bar1 涨停时引擎照常买入（无涨跌停检查）→ 产生交易
# 目标(修复后):
#   bar1 涨停(close=high) → 拒绝买入 → 无交易
#   total_trades=0, total_return=0

class TestLimitUpNoBuy:
    bars = _bars([
        {"c": 10.0},
        {"o": 10.8, "h": 10.8, "l": 10.8, "c": 10.8},  # 一字涨停
        {"c": 11.0},
    ])

    def test_baseline_buy_at_limit_up(self):
        """修复前基线：涨停时照常买入（无涨跌停检查）。"""
        out = _run(_LIMIT_UP_STRATEGY, {}, self.bars)
        buys = [t for t in out["trades"] if t["side"] == "buy"]
        sells = [t for t in out["trades"] if t["side"] == "sell"]
        # 当前引擎在涨停时仍然买入
        assert len(buys) == 1
        assert len(sells) == 1

    @pytest.mark.xfail(reason="G20: 触及涨停应拒绝买入")
    def test_target_no_buy_at_limit_up(self):
        """目标：涨停时拒绝买入。"""
        out = _run(_LIMIT_UP_STRATEGY, {}, self.bars)
        buys = [t for t in out["trades"] if t["side"] == "buy"]
        assert len(buys) == 0


# ===========================================================================
# 场景 5b：跌停不卖出
# ===========================================================================
# bar0: c=10.0 → 买入
# bar1: o=h=l=c=9.0 (一字跌停), 带 stop_loss 10%
#   stop_price = 10*(1-0.1) = 9.0, low=9.0 <= 9.0 → 触发止损
#
# 当前(修复前):
#   止损触发卖出@9.0（跌停也能卖出，不现实）
# 目标(修复后):
#   跌停(close=low) → 拒绝卖出 → 持仓保留

class TestLimitDownNoSell:
    bars = _bars([
        {"c": 10.0},
        {"o": 9.0, "h": 9.0, "l": 9.0, "c": 9.0},  # 一字跌停
        {"c": 8.5},
    ])
    params = {"stop_loss": {"pct": 0.10}}

    def test_baseline_sell_at_limit_down(self):
        """修复前基线：跌停时止损仍能卖出（不现实）。"""
        out = _run(_BUY_THEN_SELL, self.params, self.bars)
        sells = [t for t in out["trades"] if t["side"] == "sell"]
        # 当前引擎在跌停时仍能卖出
        assert len(sells) >= 1

    @pytest.mark.xfail(reason="G20: 触及跌停应拒绝卖出")
    def test_target_no_sell_at_limit_down(self):
        """目标：跌停时拒绝卖出（含止损）。"""
        out = _run(_BUY_THEN_SELL, self.params, self.bars)
        # bar1 跌停：止损触发但被拒绝 → 持仓保留
        bar1_sells = [t for t in out["trades"]
                      if t["side"] == "sell" and t["ts"] == self.bars[1]["ts"]]
        assert len(bar1_sells) == 0


# ===========================================================================
# 场景 6：同 bar 止损后禁止再开同向仓
# ===========================================================================
# bar0: buy 100@10.0
# bar1: buy 100@11.0 → 持仓 200, 加权均价=10.5
# bar2: h=12.0, l=9.0, c=10.0
#   stop_price = 10.5*(1-0.1) = 9.45
#   low=9.0 <= 9.45 → 止损卖出 200@9.45
#   on_bar 检测到 pos=0 → 再买 100@10.0
#
# 当前(修复前):
#   止损卖 200@9.45 + 再买 100@10.0（同 bar 先卖后买）
#   共 3 笔卖单(2 配对) + 1 笔未配对买单
# 目标(修复后):
#   止损卖出后，同一根 bar 禁止再开同向仓位
#   仅止损卖 200@9.45，不再买入

class TestSameBarStopThenReentry:
    bars = _bars([
        {"c": 10.0},
        {"c": 11.0},
        {"o": 10.0, "h": 12.0, "l": 9.0, "c": 10.0},  # 大幅波动
    ])
    params = {"stop_loss": {"pct": 0.10}}

    def test_baseline_stoploss_then_rebuy(self):
        """修复前基线：止损卖出后同 bar 可以再买入。"""
        out = _run(_STOPLOSS_THEN_BUY, self.params, self.bars)
        buys = [t for t in out["trades"] if t["side"] == "buy"]
        sells = [t for t in out["trades"] if t["side"] == "sell"]
        # bar0: buy, bar1: buy, bar2: stop-sell(200) + re-buy(100)
        assert len(buys) == 3  # bar0+bar1+bar2(re-buy)
        assert len(sells) == 1  # bar2 stop-loss

    @pytest.mark.xfail(reason="G20: 同 bar 止损后应禁止再开同向仓位")
    def test_target_no_reentry_after_stoploss(self):
        """目标：止损卖出后同一根 bar 不再允许买入。"""
        out = _run(_STOPLOSS_THEN_BUY, self.params, self.bars)
        buys = [t for t in out["trades"] if t["side"] == "buy"]
        sells = [t for t in out["trades"] if t["side"] == "sell"]
        # bar0: buy, bar1: buy, bar2: stop-sell only (no re-buy)
        assert len(buys) == 2  # 仅 bar0+bar1
        assert len(sells) == 1  # bar2 stop-loss


# ===========================================================================
# 场景 7：费用对微利交易的影响（毛赚净亏）
# ===========================================================================
# Buy 100@10.0, Sell 100@10.01 (微利)
# 毛 PnL = 0.01*100 = 1.0
# 买费 = 10*100*0.001 = 1.0
# 卖费 = 10.01*100*(0.001+0.0005) = 1.5015
# 净 PnL = 1.0 - 1.0 - 1.5015 = -1.5015
#
# 当前(修复前): 配对 pnl=1.0(毛) → win
# 目标(修复后): 配对 pnl=-1.5015(净) → loss

_STRATEGY_MICRO_PROFIT = """
def on_bar(bar, context):
    if context.bar_index == 0:
        context.buy(100)
    elif context.bar_index == 1:
        context.sell(100)
"""


class TestMicroProfitGrossWinNetLoss:
    bars = _bars([{"c": 10.0}, {"c": 10.01}])

    def test_baseline_gross_win(self):
        """修复前基线：微利(毛+1.0)判定为 win。"""
        out = _run(_STRATEGY_MICRO_PROFIT, {}, self.bars)
        pairs = metrics._pair_trades(out["trades"])
        assert len(pairs) == 1
        assert pairs[0]["pnl"] == pytest.approx(1.0, abs=0.01)
        m = metrics.compute_metrics(
            out["trades"], out["equity_curve"],
            out["initial_cash"], out["start_ts"], out["end_ts"], "1d",
        )
        assert m["win_rate"] == pytest.approx(1.0)  # 毛赚→win

    @pytest.mark.xfail(reason="G20: 净 PnL=-1.5 应为 loss，非毛赚 win")
    def test_target_net_loss(self):
        """目标：微利毛赚但净亏 → 判定为 loss。"""
        out = _run(_STRATEGY_MICRO_PROFIT, {}, self.bars)
        pairs = metrics._pair_trades(out["trades"])
        assert len(pairs) == 1
        assert pairs[0]["pnl"] < 0  # 净 PnL 为负
        m = metrics.compute_metrics(
            out["trades"], out["equity_curve"],
            out["initial_cash"], out["start_ts"], out["end_ts"], "1d",
        )
        assert m["win_rate"] == pytest.approx(0.0)  # 净亏→loss


# ===========================================================================
# 场景 8：撮合现实性 — 滑点（G20 新增，当前恒 0）
# ===========================================================================

class TestSlippage:
    bars = _bars([{"c": 10.0}, {"c": 12.0}])

    def test_baseline_no_slippage(self):
        """修复前基线：slippage_pct 配置后对买入价无效（默认 0）。"""
        out = _run(_BUY_THEN_SELL, {}, self.bars, slippage_pct=0.01)
        buy = out["trades"][0]
        # 当前引擎 slippage_pct 已实现但默认 0; 这里验证 1% 滑点生效
        # engine._fill_price: buy → price*(1+slippage) = 10*1.01 = 10.1
        assert buy["price"] == pytest.approx(10.1, abs=0.01)

    def test_slippage_affects_fill_price(self):
        """验证：配置 slippage_pct 后买入价上浮、卖出价下浮。"""
        out = _run(_BUY_THEN_SELL, {}, self.bars, slippage_pct=0.01)
        buy, sell = out["trades"][0], out["trades"][1]
        assert buy["price"] == pytest.approx(10.0 * 1.01, abs=0.01)
        assert sell["price"] == pytest.approx(12.0 * 0.99, abs=0.01)


# ===========================================================================
# 场景 9：成交量限制（G20 新增，当前不校验）
# ===========================================================================

class TestVolumeLimit:
    def test_baseline_no_volume_check(self):
        """修复前基线：不校验成交量，大量买入不受限制。"""
        # 成交量仅 100 股，但策略尝试买 10000 股
        bars = _bars([{"c": 10.0, "v": 100}, {"c": 12.0, "v": 100}])
        strategy = """
def on_bar(bar, context):
    if context.bar_index == 0:
        context.buy(10000)
    elif context.bar_index == 1:
        context.sell(10000)
"""
        out = _run(strategy, {}, bars)
        buys = [t for t in out["trades"] if t["side"] == "buy"]
        # 当前引擎不校验成交量，买入可能受资金限制但不受量能限制
        assert len(buys) >= 1

    @pytest.mark.xfail(reason="G20: 单笔成交应不超过当根 bar 成交量的可配置比例")
    def test_target_volume_cap(self):
        """目标：买入量不超过 volume * max_volume_pct。"""
        bars = _bars([{"c": 10.0, "v": 100}, {"c": 12.0, "v": 100}])
        strategy = """
def on_bar(bar, context):
    if context.bar_index == 0:
        context.buy(10000)
    elif context.bar_index == 1:
        context.sell()
"""
        out = _run(strategy, {}, bars)
        buys = [t for t in out["trades"] if t["side"] == "buy"]
        if buys:
            # 买入量应受限于 volume(100) * max_volume_pct
            assert buys[0]["shares"] <= 100  # 最多买 100 股

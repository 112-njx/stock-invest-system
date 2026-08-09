"""回测撮合引擎（4.1）：策略沙箱执行 + 撮合规则 + 持仓与交易流水。

借鉴 QuantDinger 策略 API（initialize / on_bar 回调）与撮合思路：
- 每根 bar：先按 params 自动止损止盈结算，再调用策略 on_bar 决策；
- 撮合价默认收盘价（fill_on="close"），"open" 模式策略触发延迟到下一根 bar 开盘成交；
- 自动止损止盈按触发价（entry ± pct）成交，不受 fill_on 影响；
- A 股 T+1：当日买入次日起方可卖出；
- 费用：佣金双边（默认万分之三）+ 印花税卖出单边（默认万分之五）；
- 时间预算：逐 bar 检查，超预算抛 BacktestTimeout（策略死循环兜底走 Celery 硬超时）。
"""

import logging
import time
from dataclasses import dataclass

from .sandbox import SandboxError, compile_strategy

logger = logging.getLogger(__name__)

_POSITION_DEFAULT_PCT = 0.95  # 默认仓位比例（可用资金 * pct 买入）
_PROGRESS_EVERY_BARS = 200  # 每 N 根 bar 回调一次进度


class BacktestError(Exception):
    """回测执行错误（不可重试：策略非法/数据问题等）。"""


class BacktestTimeout(Exception):
    """回测执行超时（时间预算耗尽）。"""


@dataclass
class BacktestConfig:
    initial_cash: float = 1_000_000
    commission_rate: float = 0.0003  # 佣金（双边）
    stamp_duty_rate: float = 0.0005  # 印花税（卖出单边）
    fill_on: str = "close"  # close / open
    slippage_pct: float = 0.0  # 滑点（第一版默认 0）
    time_budget: float = 30.0  # 秒
    period: str = "1d"  # 用于指标年化折算

    def __post_init__(self) -> None:
        if self.fill_on not in ("close", "open"):
            raise BacktestError(f"不支持的撮合价模式: {self.fill_on}")


class BacktestContext:
    """注入策略代码的运行上下文：持仓/资金/历史数据访问 + 交易触发。"""

    def __init__(self, params: dict, engine: "BacktestEngine", fill_price: float):
        self.params: dict = params or {}
        self.cash: float = engine.config.initial_cash
        self.pos: int = 0  # 持仓数量（股）
        self.entry_price: float | None = None  # 持仓成本价（无持仓为 None）
        self.price: float = fill_price  # 当前 bar 撮合参考价
        self.bar_index: int = 0
        self.history: list[dict] = []  # 已处理 bar（不含当前）
        self._engine = engine
        self._sellable = 0  # 可卖出数量（T+1 结算后）
        self._pending = 0  # 当日买入、次日方可卖出的数量
        self._current_bar: dict | None = None  # 当前处理中的 bar（下划线开头，受限代码不可访问）

    # ---- 策略便捷属性 ----
    @property
    def closes(self) -> list[float]:
        return [b["close"] for b in self.history]

    @property
    def is_holding(self) -> bool:
        return self.pos > 0

    # ---- 交易触发 ----
    def buy(self, shares: int | None = None) -> None:
        """买入。shares=None 表示按 position 仓位比例用可用资金买入。"""
        self._engine._do_buy(self, shares)

    def sell(self, shares: int | None = None) -> None:
        """卖出。shares=None 表示清仓（不超过可卖数量）。"""
        self._engine._do_sell(self, shares)

    def flat(self) -> None:
        """清仓。"""
        self._engine._do_sell(self, None)


class BacktestEngine:
    """撮合引擎：遍历 K 线 → 策略决策 → 成交 → 权益曲线。"""

    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()
        self.trades: list[dict] = []
        self.equity_curve: list[dict] = []
        # open 撮合模式挂单（策略触发后延迟到下一根 bar 开盘成交）
        self.pending_buy: int | None = None
        self.pending_sell: int | None = None

    # ---- 对外入口 ----
    def run(
        self,
        code: str,
        params: dict | None,
        bars: list[dict],
        progress_cb=None,
    ) -> dict:
        if not bars:
            raise BacktestError("标的无 K 线数据，无法回测")
        funcs = self._load_strategy(code)
        params = params or {}
        context = BacktestContext(params, self, float(bars[0]["close"]))
        self._call_init(funcs, context)

        started = time.monotonic()
        n_bars = len(bars)
        fill_on = self.config.fill_on

        for idx, bar in enumerate(bars):
            if time.monotonic() - started > self.config.time_budget:
                raise BacktestTimeout(f"回测执行超过时间预算 {self.config.time_budget}s")

            context._current_bar = bar
            # 1. T+1 结算：昨日买入转为可卖
            context._sellable += context._pending
            context._pending = 0

            # 2. open 撮合：结算昨日挂单（开盘价成交）
            if fill_on == "open":
                if self.pending_sell:
                    self._fill_sell(context, bar, self.pending_sell, reason="signal")
                    self.pending_sell = None
                if self.pending_buy:
                    self._fill_buy(context, bar, self.pending_buy, reason="signal")
                    self.pending_buy = None

            # 3. 更新参考价
            context.price = float(bar["close"])

            # 4. 自动止损止盈（先止损后止盈，按触发价成交）
            if context.pos > 0:
                self._auto_exit(context, bar)

            # 5. 策略决策
            try:
                funcs["on_bar"](bar, context)
            except Exception as e:  # noqa: BLE001
                raise BacktestError(f"策略 on_bar 执行失败(bar {idx}): {type(e).__name__}: {e}") from e

            # 6. close 撮合：策略触发的买卖按收盘价立即成交
            if fill_on == "close":
                if self.pending_sell:
                    self._fill_sell(context, bar, self.pending_sell, reason="signal")
                    self.pending_sell = None
                if self.pending_buy:
                    self._fill_buy(context, bar, self.pending_buy, reason="signal")
                    self.pending_buy = None

            # 7. 权益曲线 + 历史
            close = float(bar["close"])
            self.equity_curve.append(
                {
                    "ts": bar["ts"],
                    "equity": round(context.cash + context.pos * close, 2),
                    "cash": round(context.cash, 2),
                    "pos": context.pos,
                    "price": close,
                }
            )
            context.bar_index += 1
            context.history.append(bar)
            if progress_cb and idx % _PROGRESS_EVERY_BARS == 0:
                progress_cb(round(idx / n_bars * 100))

        return self._output(params, bars)

    # ---- 策略加载与初始化 ----
    def _load_strategy(self, code: str) -> dict:
        try:
            return compile_strategy(code)
        except SandboxError as e:
            raise BacktestError(str(e)) from e

    def _call_init(self, funcs: dict, context: BacktestContext) -> None:
        init = funcs.get("initialize")
        if not init:
            return
        try:
            init(context)
        except Exception as e:  # noqa: BLE001
            raise BacktestError(f"策略 initialize 执行失败: {type(e).__name__}: {e}") from e

    # ---- 撮合执行 ----
    def _fill_buy(self, context: BacktestContext, bar: dict, shares: int, reason: str = "signal") -> None:
        if shares is None or shares <= 0:
            return
        price = self._fill_price(bar, "buy")
        amount = price * shares
        fee = amount * self.config.commission_rate
        # 资金不足：按可买股数重算（不足一股放弃）
        max_shares = int(context.cash / (price * (1 + self.config.commission_rate)))
        if shares > max_shares:
            shares = max_shares
        if shares <= 0:
            return
        amount = price * shares
        fee = amount * self.config.commission_rate
        context.cash -= amount + fee
        context.pos += shares
        context._pending += shares  # T+1：当日不可卖
        if context.entry_price is None:
            context.entry_price = price
        else:
            context.entry_price = (context.entry_price * (context.pos - shares) + amount) / context.pos
        self.trades.append({"ts": bar["ts"], "side": "buy", "price": price, "shares": shares, "amount": amount, "fee": fee, "reason": reason})

    def _fill_sell(self, context: BacktestContext, bar: dict, shares: int, reason: str, price: float | None = None) -> None:
        if shares is None or shares <= 0:
            return
        sellable = min(shares, context._sellable)
        if sellable <= 0:
            return
        px = price if price is not None else self._fill_price(bar, "sell")
        amount = px * sellable
        fee = amount * (self.config.commission_rate + self.config.stamp_duty_rate)
        context.cash += amount - fee
        context.pos -= sellable
        context._sellable -= sellable
        if context.pos <= 0:
            context.pos = 0
            context.entry_price = None
        self.trades.append({"ts": bar["ts"], "side": "sell", "price": px, "shares": sellable, "amount": amount, "fee": fee, "reason": reason})

    # ---- 策略买卖入口 ----
    def _do_buy(self, context: BacktestContext, shares: int | None) -> None:
        if shares is None:
            pct = float((context.params or {}).get("position", {}).get("max_pct") or _POSITION_DEFAULT_PCT)
            price = context.price
            if price <= 0:
                return
            shares = int(context.cash * pct / (price * (1 + self.config.commission_rate)))
        if shares is None or shares <= 0:
            return
        if self.config.fill_on == "open":
            self.pending_buy = shares  # 延迟到下一根 bar 开盘成交
            return
        bar = context._current_bar
        self._fill_buy(context, bar, shares)

    def _do_sell(self, context: BacktestContext, shares: int | None) -> None:
        if shares is None:
            shares = context._sellable
        if shares <= 0:
            return
        if self.config.fill_on == "open":
            self.pending_sell = shares
            return
        bar = context._current_bar
        self._fill_sell(context, bar, shares, reason="signal")

    # ---- 自动止损止盈 ----
    def _auto_exit(self, context: BacktestContext, bar: dict) -> None:
        params = context.params or {}
        stop_pct = float((params.get("stop_loss") or {}).get("pct") or 0)
        take_pct = float((params.get("take_profit") or {}).get("pct") or 0)
        entry = context.entry_price or context.price
        stop_price = entry * (1 - stop_pct) if stop_pct > 0 else None
        take_price = entry * (1 + take_pct) if take_pct > 0 else None
        low, high = float(bar["low"]), float(bar["high"])
        if stop_price and low <= stop_price:
            self._fill_sell(context, bar, context._sellable, reason="stop_loss", price=stop_price)
        elif take_price and high >= take_price:
            self._fill_sell(context, bar, context._sellable, reason="take_profit", price=take_price)

    # ---- 辅助 ----
    def _fill_price(self, bar: dict, side: str) -> float:
        price = float(bar["close"])
        if self.config.fill_on == "open":
            price = float(bar["open"])
        if self.config.slippage_pct > 0:
            price *= 1 + self.config.slippage_pct if side == "buy" else 1 - self.config.slippage_pct
        return round(price, 4)

    def _output(self, params: dict, bars: list[dict]) -> dict:
        return {
            "params": params,
            "trades": self.trades,
            "equity_curve": self.equity_curve,
            "bars_used": len(bars),
            "fill_on": self.config.fill_on,
            "initial_cash": self.config.initial_cash,
            "final_equity": round(self.equity_curve[-1]["equity"], 2) if self.equity_curve else self.config.initial_cash,
            "start_ts": bars[0]["ts"] if bars else None,
            "end_ts": bars[-1]["ts"] if bars else None,
        }

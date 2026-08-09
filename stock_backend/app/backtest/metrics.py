"""回测绩效指标（4.2）：胜率/盈亏比/夏普/累计买卖/年化/最大回撤 + metrics_json 扩展。

借鉴 TradingAgents-CN 绩效指标库实现思路：
- 配对交易（FIFO 买入-卖出配对）计算胜率与盈亏比；
- 夏普/波动用权益序列的逐 bar 收益率，按周期折算年化；
- 年化收益按首末净值与时间跨度折算。
"""

from collections import deque
from datetime import datetime
from math import sqrt
from statistics import mean, pstdev

# 周期 → 每年 bar 数（A 股近似）
BARS_PER_YEAR = {"15m": 252 * 16, "1d": 252, "1w": 52, "1mon": 12}
_FALLBACK_BARS_PER_YEAR = 252


def _bars_per_year(period: str) -> int:
    return BARS_PER_YEAR.get(period, _FALLBACK_BARS_PER_YEAR)


def _pair_trades(trades: list[dict]) -> list[dict]:
    """FIFO 配对：按时间顺序，卖单与最早未平仓买单配对，返回每笔配对盈亏。"""
    buys: deque = deque()  # [{price, shares, ts}]
    pairs: list[dict] = []
    for t in trades:
        if t["side"] == "buy":
            buys.append({"price": t["price"], "shares": t["shares"], "ts": t["ts"]})
            continue
        shares_left = t["shares"]
        while shares_left > 0 and buys:
            b = buys[0]
            close_shares = min(shares_left, b["shares"])
            pnl = (t["price"] - b["price"]) * close_shares
            pairs.append({"pnl": pnl, "buy_ts": b["ts"], "sell_ts": t["ts"], "shares": close_shares})
            b["shares"] -= close_shares
            shares_left -= close_shares
            if b["shares"] == 0:
                buys.popleft()
    return pairs


def _annual_return(final_equity: float, initial_cash: float, start: datetime | None, end: datetime | None) -> float | None:
    if not start or not end or initial_cash <= 0:
        return None
    total_return = final_equity / initial_cash - 1
    years = max((end - start).days / 365.25, 1 / _FALLBACK_BARS_PER_YEAR)
    return (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1.0


def _sharpe(equity_curve: list[dict], period: str) -> float | None:
    """夏普（无风险利率 0）：逐 bar 收益率 → 年化。"""
    if len(equity_curve) < 3:
        return None
    rets = []
    prev = None
    for pt in equity_curve:
        eq = float(pt["equity"])
        if prev:
            rets.append(eq / prev - 1)
        prev = eq
    if not rets:
        return None
    std = pstdev(rets)
    if std == 0:
        return None
    mean_r = mean(rets)
    return (mean_r / std) * sqrt(_bars_per_year(period))


def _max_drawdown(equity_curve: list[dict]) -> float | None:
    if not equity_curve:
        return None
    peak = float("-inf")
    mdd = 0.0
    for pt in equity_curve:
        eq = float(pt["equity"])
        if eq > peak:
            peak = eq
        if peak > 0:
            dd = (peak - eq) / peak
            if dd > mdd:
                mdd = dd
    return mdd


def compute_metrics(
    trades: list[dict],
    equity_curve: list[dict],
    initial_cash: float,
    start_ts: datetime | None,
    end_ts: datetime | None,
    period: str = "1d",
) -> dict:
    """计算回测绩效指标（含 metrics_json 扩展字段）。"""
    final_equity = float(equity_curve[-1]["equity"]) if equity_curve else initial_cash
    pairs = _pair_trades(trades)
    total_buys = sum(1 for t in trades if t["side"] == "buy")
    total_sells = sum(1 for t in trades if t["side"] == "sell")
    commission_total = sum(float(t["fee"]) for t in trades)

    win_rate: float | None = None
    profit_loss_ratio: float | None = None
    if pairs:
        wins = [p["pnl"] for p in pairs if p["pnl"] > 0]
        losses = [p["pnl"] for p in pairs if p["pnl"] <= 0]
        win_rate = len(wins) / len(pairs) if pairs else None
        if wins and losses:
            profit_loss_ratio = abs(mean(wins) / mean(losses)) if mean(losses) != 0 else None
        elif wins:
            profit_loss_ratio = None  # 全胜无亏损，盈亏比无意义（不除 0）

    sharpe = _sharpe(equity_curve, period)
    annual_return = _annual_return(final_equity, initial_cash, start_ts, end_ts)
    max_drawdown = _max_drawdown(equity_curve)

    metrics_json: dict = {
        "total_return": round(final_equity / initial_cash - 1, 6) if initial_cash else None,
        "total_trades": len(pairs),
        "total_buys": total_buys,
        "total_sells": total_sells,
        "commission_total": round(commission_total, 2),
        "bars_used": len(equity_curve),
        "avg_holding_bars": _avg_holding_bars(equity_curve, pairs),
        "annual_volatility": _annual_volatility(equity_curve, period),
        "best_trade": round(max((p["pnl"] for p in pairs), default=0.0), 2),
        "worst_trade": round(min((p["pnl"] for p in pairs), default=0.0), 2),
    }
    return {
        "win_rate": round(win_rate, 4) if win_rate is not None else None,
        "profit_loss_ratio": round(profit_loss_ratio, 4) if profit_loss_ratio is not None else None,
        "sharpe": round(sharpe, 4) if sharpe is not None else None,
        "total_buys": total_buys,
        "total_sells": total_sells,
        "annual_return": round(annual_return, 4) if annual_return is not None else None,
        "max_drawdown": round(max_drawdown, 4) if max_drawdown is not None else None,
        "metrics_json": metrics_json,
    }


def _avg_holding_bars(equity_curve: list[dict], pairs: list[dict]) -> float | None:
    """平均持仓 bar 数：按配对区间（买→卖）bar 数均值，简化用 equity 的持仓段。"""
    if not pairs:
        return None
    holding = 0
    episodes = 0
    in_holding = False
    for pt in equity_curve:
        pos = int(pt.get("pos", 0))
        if pos > 0 and not in_holding:
            in_holding = True
            episodes += 1
        if pos > 0:
            holding += 1
        elif in_holding:
            in_holding = False
    return round(holding / episodes, 2) if episodes else None


def _annual_volatility(equity_curve: list[dict], period: str) -> float | None:
    if len(equity_curve) < 3:
        return None
    rets = []
    prev = None
    for pt in equity_curve:
        eq = float(pt["equity"])
        if prev:
            rets.append(eq / prev - 1)
        prev = eq
    return round(pstdev(rets) * sqrt(_bars_per_year(period)), 4) if rets else None

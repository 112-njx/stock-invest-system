"""回测绩效指标（4.2 → P0-10b 修复）：净盈亏胜率/回合口径/夏普/回撤/期末结算。

P0-10b 修复要点（G20）：
- 配对 PnL 扣除对应买卖费用 → 净盈亏判定 win/loss
- 平手（毛 PnL=0）标记为 draw，不计入亏损
- total_trades 按完整交易回合计数（FIFO 仅用于成本分摊）
- 期末未平仓浮动结算 → unrealized_pnl/unrealized_count
- best/worst_trade 用净 PnL
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
    """FIFO 配对（G20 修复版）：每笔配对含净 PnL（扣除费用）与完整回合标记。

    返回字段：
    - pnl: 毛 PnL = (sell_price - buy_price) * shares
    - net_pnl: 净 PnL = pnl - allocated_buy_fee - allocated_sell_fee
    - round_close: True = 此配对闭合一个完整交易回合
    """
    buys: deque = deque()  # [{price, shares, ts, fee, orig_shares}]
    pairs: list[dict] = []

    # 回合追踪
    round_buy_shares = 0
    round_sell_shares = 0

    for t in trades:
        if t["side"] == "buy":
            shares = t["shares"]
            buys.append({
                "price": t["price"],
                "shares": shares,
                "ts": t["ts"],
                "fee": float(t.get("fee", 0)),
                "orig_shares": shares,
            })
            round_buy_shares += shares
            continue

        # Sell
        shares_left = t["shares"]
        sell_fee_total = float(t.get("fee", 0))
        sell_shares_total = t["shares"]

        while shares_left > 0 and buys:
            b = buys[0]
            close_shares = min(shares_left, b["shares"])

            # 毛 PnL
            pnl = (t["price"] - b["price"]) * close_shares

            # 费用分摊（按配对股数占比）
            buy_fee_alloc = b["fee"] * (close_shares / b["orig_shares"]) if b["orig_shares"] > 0 else 0
            sell_fee_alloc = sell_fee_total * (close_shares / sell_shares_total) if sell_shares_total > 0 else 0
            net_pnl = pnl - buy_fee_alloc - sell_fee_alloc

            # 扣减买单剩余
            b["shares"] -= close_shares
            b["fee"] -= buy_fee_alloc
            shares_left -= close_shares
            round_sell_shares += close_shares

            # 判断回合是否闭合
            is_round_close = False
            if round_sell_shares >= round_buy_shares and round_buy_shares > 0:
                is_round_close = True
                round_buy_shares = 0
                round_sell_shares = 0

            pairs.append({
                "pnl": round(pnl, 6),
                "net_pnl": round(net_pnl, 6),
                "buy_ts": b["ts"],
                "sell_ts": t["ts"],
                "shares": close_shares,
                "round_close": is_round_close,
            })

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
    open_position: dict | None = None,
) -> dict:
    """计算回测绩效指标（G20 修复版：净盈亏 + 回合口径 + 期末结算 + draw）。

    open_position: {"shares": int, "fifo_cost": float, "last_close": float} 或 None
    """
    final_equity = float(equity_curve[-1]["equity"]) if equity_curve else initial_cash
    pairs = _pair_trades(trades)
    total_buys = sum(1 for t in trades if t["side"] == "buy")
    total_sells = sum(1 for t in trades if t["side"] == "sell")
    commission_total = sum(float(t.get("fee", 0)) for t in trades)

    # ---- 分类（G20：净盈亏 + draw）----
    win_rate: float | None = None
    profit_loss_ratio: float | None = None
    draw_count = 0

    if pairs:
        wins = []
        losses = []
        for p in pairs:
            gross = p["pnl"]
            net = p.get("net_pnl", gross)
            if gross == 0:
                # 毛盈亏为零 → draw（平手），不计入 win/loss 统计
                draw_count += 1
            elif net > 0:
                wins.append(net)
            else:
                losses.append(net)

        non_draw = len(pairs) - draw_count
        win_rate = len(wins) / non_draw if non_draw > 0 else None

        if wins and losses:
            profit_loss_ratio = abs(mean(wins) / mean(losses)) if mean(losses) != 0 else None
        elif wins:
            profit_loss_ratio = None  # 全胜无亏损

    # ---- 期末未平仓浮动结算 ----
    unrealized_pnl = 0.0
    unrealized_count = 0
    if open_position and open_position.get("shares", 0) > 0:
        shares = open_position["shares"]
        fifo_cost = open_position.get("fifo_cost", 0)
        last_close = open_position.get("last_close", 0)
        unrealized_pnl = round((last_close - fifo_cost) * shares, 2)
        unrealized_count = 1

    # ---- 完整回合统计 ----
    total_rounds = sum(1 for p in pairs if p.get("round_close", False))

    sharpe = _sharpe(equity_curve, period)
    annual_return = _annual_return(final_equity, initial_cash, start_ts, end_ts)
    max_drawdown = _max_drawdown(equity_curve)

    # best/worst 用净 PnL
    net_pnls = [p.get("net_pnl", p["pnl"]) for p in pairs]
    best_trade = round(max(net_pnls), 2) if net_pnls else 0.0
    worst_trade = round(min(net_pnls), 2) if net_pnls else 0.0

    metrics_json: dict = {
        "total_return": round(final_equity / initial_cash - 1, 6) if initial_cash else None,
        "total_trades": total_rounds,
        "total_buys": total_buys,
        "total_sells": total_sells,
        "commission_total": round(commission_total, 2),
        "bars_used": len(equity_curve),
        "avg_holding_bars": _avg_holding_bars(equity_curve, pairs),
        "annual_volatility": _annual_volatility(equity_curve, period),
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "draws": draw_count,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_count": unrealized_count,
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

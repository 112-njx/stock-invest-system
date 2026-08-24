"""V0.2 第三波（阶段八 8.5）：strategy_templates 策略模板表 + 5 个内置模板种子（幂等）。

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("params_schema", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.bulk_insert(
        sa.table(
            "strategy_templates",
            sa.column("name", sa.String()),
            sa.column("description", sa.Text()),
            sa.column("code", sa.Text()),
            sa.column("params_schema", sa.JSON()),
            sa.column("sort_order", sa.Integer()),
        ),
        [
            {
                "name": "双均线交叉",
                "description": "短期均线上穿长期均线买入，下穿卖出。经典趋势跟随，适合趋势行情，震荡市可能反复止损。",
                "code": _DOUBLE_MA_CODE,
                "params_schema": {
                    "entry": {"fast": 5, "slow": 20},
                    "stop_loss": {"pct": 0.05},
                    "take_profit": {"pct": 0.10},
                    "position": {"max_pct": 0.95},
                },
                "sort_order": 1,
            },
            {
                "name": "MACD金叉死叉",
                "description": "MACD 的 DIF 上穿 DEA（金叉）买入，下穿（死叉）卖出，动量趋势策略。",
                "code": _MACD_CODE,
                "params_schema": {
                    "entry": {"fast": 12, "slow": 26, "signal": 9},
                    "stop_loss": {"pct": 0.05},
                    "take_profit": {"pct": 0.12},
                    "position": {"max_pct": 0.95},
                },
                "sort_order": 2,
            },
            {
                "name": "KDJ超买超卖",
                "description": "KDJ 的 K 值超卖（<20）买入、超买（>80）卖出，震荡市反转策略。",
                "code": _KDJ_CODE,
                "params_schema": {
                    "entry": {"oversold": 20, "overbought": 80},
                    "stop_loss": {"pct": 0.04},
                    "take_profit": {"pct": 0.08},
                    "position": {"max_pct": 0.95},
                },
                "sort_order": 3,
            },
            {
                "name": "布林带突破",
                "description": "收盘价上穿布林带上轨买入、下穿中轨卖出，波动率突破策略。",
                "code": _BOLL_CODE,
                "params_schema": {
                    "entry": {"period": 20, "mult": 2.0},
                    "stop_loss": {"pct": 0.05},
                    "take_profit": {"pct": 0.10},
                    "position": {"max_pct": 0.95},
                },
                "sort_order": 4,
            },
            {
                "name": "成交量异动",
                "description": "成交量放大（当日量 > N 日均量 × 倍数）且上涨时买入，量能衰竭卖出。",
                "code": _VOLUME_CODE,
                "params_schema": {
                    "entry": {"vol_period": 5, "vol_mult": 1.5},
                    "stop_loss": {"pct": 0.05},
                    "take_profit": {"pct": 0.10},
                    "position": {"max_pct": 0.95},
                },
                "sort_order": 5,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("strategy_templates")


# ---- 模板代码（本项目沙箱接口：initialize(context) + on_bar(bar, context)）----
_DOUBLE_MA_CODE = '''def initialize(context):
    context.params.setdefault("fast", 5)
    context.params.setdefault("slow", 20)


def on_bar(bar, context):
    fast = int(context.params.get("fast", 5))
    slow = int(context.params.get("slow", 20))
    if fast >= slow:
        return
    closes = context.closes
    if len(closes) < slow + 1:
        return
    ma_fast = sum(closes[-fast:]) / fast
    ma_slow = sum(closes[-slow:]) / slow
    prev_fast = sum(closes[-fast - 1:-1]) / fast
    prev_slow = sum(closes[-slow - 1:-1]) / slow
    if prev_fast <= prev_slow and ma_fast > ma_slow and not context.is_holding:
        context.buy()
    elif prev_fast >= prev_slow and ma_fast < ma_slow and context.is_holding:
        context.sell()
'''

_MACD_CODE = '''def ema(values, period):
    k = 2.0 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def initialize(context):
    context.params.setdefault("fast", 12)
    context.params.setdefault("slow", 26)
    context.params.setdefault("signal", 9)
    context.dif_hist = []


def on_bar(bar, context):
    fast = int(context.params.get("fast", 12))
    slow = int(context.params.get("slow", 26))
    signal = int(context.params.get("signal", 9))
    closes = context.closes
    if len(closes) < slow + 1:
        return
    hist = closes + [float(bar["close"])]
    dif = ema(hist, fast) - ema(hist, slow)
    context.dif_hist.append(dif)
    if len(context.dif_hist) < signal + 1:
        return
    dea = ema(context.dif_hist, signal)
    prev_dea = ema(context.dif_hist[:-1], signal)
    prev_dif = context.dif_hist[-2]
    if prev_dif <= prev_dea and dif > dea and not context.is_holding:
        context.buy()
    elif prev_dif >= prev_dea and dif < dea and context.is_holding:
        context.sell()
'''

_KDJ_CODE = '''def rsv(closes, highs, lows, period=9):
    low_n = min(lows[-period:])
    high_n = max(highs[-period:])
    if high_n == low_n:
        return 50.0
    return (closes[-1] - low_n) / (high_n - low_n) * 100.0


def initialize(context):
    context.params.setdefault("oversold", 20)
    context.params.setdefault("overbought", 80)
    context.k_prev = 50.0


def on_bar(bar, context):
    oversold = float(context.params.get("oversold", 20))
    overbought = float(context.params.get("overbought", 80))
    closes = context.closes
    highs = [b["high"] for b in context.history]
    lows = [b["low"] for b in context.history]
    if len(closes) < 9:
        return
    cur_rsv = rsv(closes + [float(bar["close"])], highs + [float(bar["high"])], lows + [float(bar["low"])])
    k = (2 * context.k_prev + cur_rsv) / 3
    prev_k = context.k_prev
    context.k_prev = k
    if prev_k < oversold and k >= oversold and not context.is_holding:
        context.buy()
    elif prev_k > overbought and k <= overbought and context.is_holding:
        context.sell()
'''

_BOLL_CODE = '''def initialize(context):
    context.params.setdefault("period", 20)
    context.params.setdefault("mult", 2.0)


def on_bar(bar, context):
    period = int(context.params.get("period", 20))
    mult = float(context.params.get("mult", 2.0))
    closes = context.closes
    if len(closes) < period:
        return
    recent = closes[-period:] + [float(bar["close"])]
    prev = closes[-period:]
    mid = sum(recent) / len(recent)
    prev_mid = sum(prev) / len(prev)
    var = sum((c - mid) ** 2 for c in recent) / len(recent)
    std = var ** 0.5
    upper = mid + mult * std
    prev_upper = prev_mid + mult * (sum((c - prev_mid) ** 2 for c in prev) / len(prev)) ** 0.5
    close = float(bar["close"])
    if prev_upper >= close and close > upper and not context.is_holding:
        context.buy()
    elif close < mid and context.is_holding:
        context.sell()
'''

_VOLUME_CODE = '''def initialize(context):
    context.params.setdefault("vol_period", 5)
    context.params.setdefault("vol_mult", 1.5)


def on_bar(bar, context):
    period = int(context.params.get("vol_period", 5))
    mult = float(context.params.get("vol_mult", 1.5))
    vols = [b["volume"] for b in context.history]
    if len(vols) < period:
        return
    avg_vol = sum(vols[-period:]) / period
    cur_vol = float(bar["volume"])
    prev_close = context.closes[-1] if context.closes else float(bar["open"])
    close = float(bar["close"])
    if cur_vol > avg_vol * mult and close > prev_close and not context.is_holding:
        context.buy()
    elif cur_vol < avg_vol * 0.5 and context.is_holding:
        context.sell()
'''

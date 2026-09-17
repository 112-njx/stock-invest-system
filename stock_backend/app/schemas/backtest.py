"""回测域响应/请求模型（阶段四，统一由 {code, msg, data} 包裹）。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_PERIOD_RE = r"^(15m|1d|1w|1mon)$"
_FILL_RE = r"^(close|open)$"


class BacktestCreateIn(BaseModel):
    strategy_id: int = Field(..., gt=0, description="策略 ID（须属于当前用户）")
    symbol: str = Field(..., min_length=1, max_length=32, description="回测标的（6位代码或 symbol_id）")
    period: str = Field("1d", pattern=_PERIOD_RE, description="K 线周期 15m|1d|1w|1mon")
    start: datetime | None = Field(None, description="回测起始时间（默认最近 N 天）")
    end: datetime | None = Field(None, description="回测结束时间（默认当前）")
    fill_on: str = Field("close", pattern=_FILL_RE, description="撮合价 close|open")


class BacktestTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    symbol_id: int
    status: str  # queued/running/success/failed
    progress: int
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class BacktestResultBriefOut(BaseModel):
    """列表用精简结果（G32）：不含 equity_curve/trades（单条约 60KB，避免列表接口膨胀）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    strategy_id: int
    symbol_id: int
    win_rate: float | None = None
    profit_loss_ratio: float | None = None
    sharpe: float | None = None
    total_buys: int | None = None
    total_sells: int | None = None
    annual_return: float | None = None
    max_drawdown: float | None = None
    metrics_json: dict[str, Any] | None = None
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    created_at: datetime


class BacktestResultOut(BacktestResultBriefOut):
    """详情用结果（G32）：含资金曲线与买卖流水。

    equity_curve 元素：{ts(ISO8601), equity, cash, pos, price}
    trades 元素：{ts(ISO8601), side(buy|sell), price, shares, amount, fee,
                 reason(signal|stop_loss|take_profit), realized_pnl(卖出为净盈亏，买入为 null)}
    存量结果行（0013 迁移前）两列为 null，前端按空态降级。
    """

    equity_curve: list[dict[str, Any]] | None = None
    trades: list[dict[str, Any]] | None = None

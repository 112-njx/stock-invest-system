"""回测域响应/请求模型（阶段四，统一由 {code, msg, data} 包裹）。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_PERIOD_RE = r"^(15m|1d|1w|1mon)$"
_FILL_RE = r"^(close|open)$"


class BacktestCreateIn(BaseModel):
    strategy_id: int = Field(..., gt=0, description="策略 ID（须属于当前用户）")
    symbol: str = Field(..., min_length=1, description="回测标的（6位代码或 symbol_id）")
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


class BacktestResultOut(BaseModel):
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

"""行情域响应模型（统一由 {code, msg, data} 包裹）。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SymbolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    type: str
    market: str
    industry: str | None = None
    etf_linked: str | None = None
    is_fixed_index: bool = False
    sort_order: int | None = None


class KlineBarOut(BaseModel):
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float


class SnapshotOut(BaseModel):
    """实时快照（合并特殊字段）。特殊字段按类型注入 extra。"""

    symbol_id: int
    code: str
    name: str
    type: str
    price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    pre_close: float | None = None
    volume: int | None = None
    amount: float | None = None
    turnover: float | None = None
    amplitude: float | None = None
    updated_at: datetime | None = None
    extra: dict[str, Any] = {}  # stock: {market_cap, pe} / etf: {nav, premium} / index: {pe}

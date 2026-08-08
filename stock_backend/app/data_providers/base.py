"""行情源抽象基类：可插拔（默认东方财富/Akshare，可新增供应商）。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class KlineBar:
    """单根 K 线（ts 为 UTC）。"""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float


@dataclass
class RealtimeSymbol:
    """待查询实时快照的标的（行业指数 code 可能为空，用 name 匹配）。"""

    code: str = ""
    name: str = ""
    asset_type: str = "stock"  # stock / etf / index / industry_index


@dataclass
class RealtimeQuote:
    """实时快照（字段与 snapshot_realtime 对齐；无数据时置 None）。"""

    code: str = ""
    name: str = ""
    asset_type: str = "stock"
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
    available: bool = True
    extra: dict = field(default_factory=dict)  # 特殊字段（fundamentals/etf_premiums 等）


class BaseDataProvider(ABC):
    """行情源抽象接口。"""

    name: str = "base"

    @abstractmethod
    def fetch_kline(
        self,
        symbol: str,
        period: str,
        start: datetime,
        end: datetime,
        asset_type: str = "stock",
    ) -> list[KlineBar]:
        """拉取历史 K 线。

        period: 15m / 1d / 1w / 1mon
        asset_type: stock / etf / index / industry_index（industry_index 时 symbol 传板块名称）
        """

    @abstractmethod
    def fetch_realtime(self, symbols: list[RealtimeSymbol]) -> list[RealtimeQuote]:
        """批量实时快照（内部按资产类型分组拉取，缺数置 available=False）。"""

    @abstractmethod
    def resolve_index_code(self, name: str) -> str | None:
        """行业指数名称 → 东方财富板块代码（BKxxxx），用于回填 symbols.code。"""

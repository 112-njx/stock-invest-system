"""行情源抽象基类：可插拔（默认东方财富/Akshare，可新增供应商）。

统一封装请求超时/指数退避重试（_call）与 Provider 服务范围判定（can_fetch_*），
供 DataProviderFactory 按优先级链熔断降级复用。
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """外部源彻底失败（重试耗尽）：用于工厂熔断判断与降级链切换。"""


def _to_float(v) -> float | None:
    """容错转 float：None/NaN/坏值返回 None。"""
    import pandas as pd

    if v is None or pd.isna(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def unavailable_quote(s: "RealtimeSymbol") -> "RealtimeQuote":
    """构造不可用快照（数据源未命中/全失败时返回，保持调用方 zip 对齐契约）。"""
    return RealtimeQuote(code=s.code, name=s.name, asset_type=s.asset_type, available=False)


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
    probe_symbol = "000001"  # 熔断探测固定标的
    probe_asset_type = "index"

    def __init__(self) -> None:
        settings = get_settings()
        self.timeout = settings.SYNC_TIMEOUT
        self.retry_times = settings.SYNC_RETRY_TIMES
        self.retry_backoff = settings.SYNC_RETRY_BACKOFF

    # ---- 通用调用封装 ----
    def _call(self, fn, retry_times: int | None = None, raise_on_giveup: bool = False, **kwargs):
        """带指数退避重试的外部调用。

        raise_on_giveup=True 时重试耗尽抛 ProviderError（供工厂熔断/降级识别）；
        默认 lenient 返回 None（best-effort 场景：指数 PE、板块名映射等）。
        """
        retries = self.retry_times if retry_times is None else retry_times
        last_exc = None
        for attempt in range(retries):
            try:
                return fn(**kwargs)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait = self.retry_backoff * (2**attempt)
                logger.warning(
                    "[provider:%s] %s failed (attempt %d): %s, retry in %.1fs",
                    self.name,
                    getattr(fn, "__name__", fn),
                    attempt + 1,
                    str(exc)[:120],
                    wait,
                )
                time.sleep(wait)
        logger.error("[provider:%s] %s give up: %s", self.name, getattr(fn, "__name__", fn), last_exc)
        if raise_on_giveup:
            raise ProviderError(f"{getattr(fn, '__name__', fn)} give up: {last_exc}") from last_exc
        return None

    # ---- 服务范围判定（工厂据此跳过不适用 Provider）----
    def can_fetch_kline(self, asset_type: str, period: str) -> bool:
        """是否支持该资产类型/周期的历史K线。"""
        return True

    def can_fetch_realtime(self) -> bool:
        """是否支持实时快照。"""
        return True

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

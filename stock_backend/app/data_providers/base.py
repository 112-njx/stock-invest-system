"""行情源抽象基类：可插拔（默认东方财富/Akshare，可新增供应商）。

统一封装请求超时/指数退避重试（_call）与 Provider 服务范围判定（can_fetch_*），
供 DataProviderFactory 按优先级链熔断降级复用。
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
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
    source: str = "stockdb"


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
        默认 lenient 返回 None（best-effort 场景：板块名映射等）。
        """
        retries = self.retry_times if retry_times is None else retry_times
        last_exc = None
        from app.data_providers.request_activity import ActiveProviderRequest

        activity = ActiveProviderRequest(self.name, fn, kwargs)
        try:
            for attempt in range(retries):
                try:
                    from app.data_providers.traffic import acquire

                    activity.update("throttling", attempt + 1, retries)
                    acquire(self.name)
                    activity.update("requesting", attempt + 1, retries)
                    return fn(**kwargs)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    from app.utils.redis_client import get_redis_client

                    wait = float(get_redis_client().get('provider:retry:interval') or self.retry_backoff)
                    logger.warning(
                        "[provider:%s] %s failed (attempt %d): %s, retry in %.1fs",
                        self.name,
                        getattr(fn, "__name__", fn),
                        attempt + 1,
                        str(exc)[:120],
                        wait,
                    )
                    if attempt < retries - 1:
                        activity.update("retry_wait", attempt + 1, retries, wait)
                        time.sleep(wait)
            logger.error("[provider:%s] %s give up: %s", self.name, getattr(fn, "__name__", fn), last_exc)
            if raise_on_giveup:
                raise ProviderError(f"{getattr(fn, '__name__', fn)} give up: {last_exc}") from last_exc
            return None
        finally:
            activity.close()

    # ---- 服务范围判定（工厂据此跳过不适用 Provider）----
    def can_fetch_kline(self, asset_type: str, period: str) -> bool:
        """是否支持该资产类型/周期的历史K线。"""
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
    def resolve_index_code(self, name: str) -> str | None:
        """行业指数名称 → 东方财富板块代码（BKxxxx），用于回填 symbols.code。"""

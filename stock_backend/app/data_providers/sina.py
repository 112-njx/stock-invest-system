"""新浪行情提供器：A 股大盘指数日K 降级兜底（stock_zh_index_daily，仅 index 1d）。

原为 EastMoneyProvider 内嵌降级逻辑，V0.2 阶段四拆分为独立 Provider，供工厂按优先级链熔断降级。
"""

import logging
from datetime import UTC

import pandas as pd

from .base import BaseDataProvider, KlineBar, _to_float

logger = logging.getLogger(__name__)


def to_sina_index(code: str) -> str | None:
    """东方财富指数代码 → 新浪指数代码（sh/sz 前缀），非 A 股指数返回 None。"""
    if code.startswith(("399", "932")):
        return f"sz{code}"
    if code.startswith(("000", "6")):
        return f"sh{code}"
    return None


class SinaProvider(BaseDataProvider):
    name = "sina"
    probe_asset_type = "index"

    def __init__(self) -> None:
        super().__init__()
        import akshare as ak

        self._ak = ak

    def can_fetch_kline(self, asset_type: str, period: str) -> bool:
        return asset_type == "index" and period == "1d"

    def can_fetch_realtime(self) -> bool:
        return False

    def fetch_kline(
        self,
        symbol: str,
        period: str,
        start,
        end,
        asset_type: str = "stock",
    ) -> list[KlineBar]:
        if not self.can_fetch_kline(asset_type, period):
            return []
        sina_symbol = to_sina_index(symbol)
        if not sina_symbol:
            return []
        df = self._call(self._ak.stock_zh_index_daily, symbol=sina_symbol, raise_on_giveup=True)
        if df is None or df.empty:
            return []
        bars: list[KlineBar] = []
        for _, row in df.iterrows():
            try:
                ts = pd.to_datetime(row["date"]).to_pydatetime().replace(tzinfo=UTC)
            except Exception:  # noqa: BLE001
                continue
            if not (start <= ts <= end):
                continue
            o = _to_float(row.get("open"))
            h = _to_float(row.get("high"))
            low = _to_float(row.get("low"))
            c = _to_float(row.get("close"))
            if o is None or c is None or h is None or low is None or h < low:
                continue
            bars.append(
                KlineBar(
                    ts=ts,
                    open=o,
                    high=h,
                    low=low,
                    close=c,
                    volume=int(_to_float(row.get("volume")) or 0),
                    amount=0.0,  # 新浪指数日K无成交额，置 0
                )
            )
        return bars

    def fetch_realtime(self, symbols) -> list:
        return []

    def resolve_index_code(self, name: str) -> str | None:
        return None

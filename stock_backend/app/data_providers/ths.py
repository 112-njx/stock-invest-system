"""同花顺行情提供器：行业板块指数日K 降级兜底（stock_board_industry_index_ths，仅 industry_index 1d）。

原为 EastMoneyProvider 内嵌降级逻辑，V0.2 阶段四拆分为独立 Provider，供工厂按优先级链熔断降级。
"""

import logging
from datetime import UTC

import pandas as pd

from .base import BaseDataProvider, KlineBar, _to_float

logger = logging.getLogger(__name__)


class THSProvider(BaseDataProvider):
    name = "ths"
    probe_symbol = "半导体"
    probe_asset_type = "industry_index"

    def __init__(self) -> None:
        super().__init__()
        import akshare as ak

        self._ak = ak

    def can_fetch_kline(self, asset_type: str, period: str) -> bool:
        return asset_type == "industry_index" and period == "1d"

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
        df = self._call(
            self._ak.stock_board_industry_index_ths,
            symbol=symbol,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            raise_on_giveup=True,
        )
        if df is None or df.empty:
            return []
        bars: list[KlineBar] = []
        for _, row in df.iterrows():
            try:
                ts = pd.to_datetime(row["日期"]).to_pydatetime().replace(tzinfo=UTC)
            except Exception:  # noqa: BLE001
                continue
            o = _to_float(row.get("开盘价"))
            h = _to_float(row.get("最高价"))
            low = _to_float(row.get("最低价"))
            c = _to_float(row.get("收盘价"))
            if o is None or c is None or h is None or low is None or h < low:
                continue
            bars.append(
                KlineBar(
                    ts=ts,
                    open=o,
                    high=h,
                    low=low,
                    close=c,
                    volume=int(_to_float(row.get("成交量")) or 0),
                    amount=_to_float(row.get("成交额")) or 0.0,
                )
            )
        return bars

    def fetch_realtime(self, symbols) -> list:
        return []

    def resolve_index_code(self, name: str) -> str | None:
        return None

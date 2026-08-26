"""新浪行情提供器：A 股大盘指数日K 降级兜底（stock_zh_index_daily）+ A股/指数实时降级源。

- K线：仅 index 1d（stock_zh_index_daily）。
- 实时：A股 stock_zh_a_spot + 指数 stock_zh_index_spot_sina（东财被限流时降级）。
原为 EastMoneyProvider 内嵌降级逻辑，V0.2 阶段四拆分为独立 Provider，供工厂按优先级链熔断降级。
"""

import logging
import re
from datetime import UTC

import pandas as pd

from .base import (
    BaseDataProvider,
    KlineBar,
    RealtimeQuote,
    RealtimeSymbol,
    _to_float,
    unavailable_quote,
)

logger = logging.getLogger(__name__)

# 新浪实时代码形如 sh600519/sz399001，去前缀后与东财无前缀代码对齐
_SINA_PREFIX = re.compile(r"^(sh|sz|bj)")


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
        return True

    def can_fetch_realtime_type(self, asset_type: str) -> bool:
        return asset_type in ("stock", "index")

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

    def fetch_realtime(self, symbols: list[RealtimeSymbol]) -> list[RealtimeQuote]:
        """A股/指数实时快照（新浪降级源）：按资产类型分组拉取，缺数置 available=False。

        新浪实时代码带 sh/sz 前缀，映射时去前缀后按代码精确匹配（匹配失败回退名称）。
        """
        by_type: dict[str, list[RealtimeSymbol]] = {}
        for s in symbols:
            by_type.setdefault(s.asset_type, []).append(s)
        quotes: list[RealtimeQuote] = []
        for atype, items in by_type.items():
            if atype == "stock":
                df = self._call(self._ak.stock_zh_a_spot, retry_times=1, raise_on_giveup=True)
                if df is None or df.empty:
                    quotes.extend(unavailable_quote(s) for s in items)
                else:
                    quotes.extend(_map_sina_spot(df, s) for s in items)
            elif atype == "index":
                df = self._call(self._ak.stock_zh_index_spot_sina, retry_times=1, raise_on_giveup=True)
                if df is None or df.empty:
                    quotes.extend(unavailable_quote(s) for s in items)
                else:
                    quotes.extend(_map_sina_spot(df, s) for s in items)
            else:  # etf / industry_index 新浪不覆盖
                quotes.extend(unavailable_quote(s) for s in items)
        return quotes

    def resolve_index_code(self, name: str) -> str | None:
        return None


def _map_sina_spot(df: pd.DataFrame, s: RealtimeSymbol) -> RealtimeQuote:
    """新浪实时表按代码（去 sh/sz 前缀）定位标的并映射字段；命中失败回退名称。"""
    q = unavailable_quote(s)
    try:
        if "代码" in df.columns:
            hit = df[
                df["代码"].astype(str).str.strip().map(lambda c: _SINA_PREFIX.sub("", c.strip())) == s.code.strip()
            ]
            if hit.empty and "名称" in df.columns:
                hit = df[df["名称"].astype(str).str.strip() == s.name.strip()]
        elif "名称" in df.columns:
            hit = df[df["名称"].astype(str).str.strip() == s.name.strip()]
        else:
            return q
        if hit.empty:
            return q
        row = hit.iloc[0]
        q = RealtimeQuote(
            code=s.code,
            name=str(row.get("名称", s.name)),
            asset_type=s.asset_type,
            price=_to_float(row.get("最新价")),
            change=_to_float(row.get("涨跌额")),
            change_pct=_to_float(row.get("涨跌幅")),
            open=_to_float(row.get("今开")),
            high=_to_float(row.get("最高")),
            low=_to_float(row.get("最低")),
            pre_close=_to_float(row.get("昨收")),
            volume=int(_to_float(row.get("成交量")) or 0) if "成交量" in row.index else None,
            amount=_to_float(row.get("成交额")) if "成交额" in row.index else None,
            available=True,
        )
        return q
    except Exception:  # noqa: BLE001
        return q

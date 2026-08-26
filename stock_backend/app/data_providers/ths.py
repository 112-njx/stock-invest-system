"""同花顺行情提供器：行业板块指数日K 降级兜底（stock_board_industry_index_ths）+ 行业实时降级源。

- K线：仅 industry_index 1d（stock_board_industry_index_ths）。
- 实时：行业板块 stock_board_industry_summary_ths（东财被限流时降级，均价近似现价）。
- code 回填：stock_board_industry_name_ths（名称→881xxx 板块代码，东财被限流时兜底）。
原为 EastMoneyProvider 内嵌降级逻辑，V0.2 阶段四拆分为独立 Provider，供工厂按优先级链熔断降级。
"""

import logging
import time
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
from .eastmoney import _MIN_INDUSTRY_SCORE, _industry_score

logger = logging.getLogger(__name__)


class THSProvider(BaseDataProvider):
    name = "ths"
    probe_symbol = "半导体"
    probe_asset_type = "industry_index"

    def __init__(self) -> None:
        super().__init__()
        import akshare as ak

        self._ak = ak
        self._board_map_cache: tuple[float, dict[str, str]] | None = None  # (ts, {名称: 881xxx})
        self._board_map_ttl = 3600  # 秒

    def can_fetch_kline(self, asset_type: str, period: str) -> bool:
        return asset_type == "industry_index" and period == "1d"

    def can_fetch_realtime(self) -> bool:
        return True

    def can_fetch_realtime_type(self, asset_type: str) -> bool:
        return asset_type == "industry_index"

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

    def fetch_realtime(self, symbols: list[RealtimeSymbol]) -> list[RealtimeQuote]:
        """行业板块实时（同花顺降级源）：仅 industry_index，其余类型置 unavailable。

        同花顺行业一览表无板块指数"最新价"，以"均价"近似现价；涨跌额/OHLC/换手/振幅缺省，
        由同步层 _fill_industry_quote_from_kline 用日K推导补全。
        """
        by_type: dict[str, list[RealtimeSymbol]] = {}
        for s in symbols:
            by_type.setdefault(s.asset_type, []).append(s)
        quotes: list[RealtimeQuote] = []
        for atype, items in by_type.items():
            if atype == "industry_index":
                df = self._call(self._ak.stock_board_industry_summary_ths, retry_times=1, raise_on_giveup=True)
                if df is None or df.empty:
                    quotes.extend(unavailable_quote(s) for s in items)
                else:
                    quotes.extend(_map_ths_industry(df, s) for s in items)
            else:  # stock/etf/index 同花顺不覆盖
                quotes.extend(unavailable_quote(s) for s in items)
        return quotes

    def resolve_index_code(self, name: str) -> str | None:
        """行业名称 → 同花顺板块代码（881xxx）：精确 → 评分模糊匹配（复用东财评分）。"""
        board_map = self._board_map()
        if not board_map:
            return None
        if name in board_map:
            return board_map[name]
        best_code: str | None = None
        best_score = _MIN_INDUSTRY_SCORE
        for ths_name, code in board_map.items():
            score = _industry_score(name, ths_name)
            if score > best_score:
                best_score, best_code = score, code
        return best_code

    def _board_map(self) -> dict[str, str]:
        now = time.time()
        if self._board_map_cache and now - self._board_map_cache[0] < self._board_map_ttl:
            return self._board_map_cache[1]
        ak = self._ak
        df = self._call(ak.stock_board_industry_name_ths)
        mapping: dict[str, str] = {}
        if df is not None and not df.empty and "name" in df.columns and "code" in df.columns:
            for _, row in df.iterrows():
                mapping[str(row["name"]).strip()] = str(row["code"]).strip()
        self._board_map_cache = (now, mapping)
        return mapping


def _map_ths_industry(df: pd.DataFrame, s: RealtimeSymbol) -> RealtimeQuote:
    q = unavailable_quote(s)
    try:
        if "板块" not in df.columns:
            return q
        hit = _match_ths_row(df, s)
        if hit.empty:
            return q
        row = hit.iloc[0]
        return RealtimeQuote(
            code=s.code,
            name=s.name,
            asset_type=s.asset_type,
            price=_to_float(row.get("均价")),
            change=None,  # 同花顺行业一览表无涨跌额
            change_pct=_to_float(row.get("涨跌幅")),
            volume=int(_to_float(row.get("总成交量")) or 0) if "总成交量" in row.index else None,
            amount=_to_float(row.get("总成交额")) if "总成交额" in row.index else None,
            available=True,
        )
    except Exception:  # noqa: BLE001
        return q


def _match_ths_row(df: pd.DataFrame, s: RealtimeSymbol) -> pd.DataFrame:
    """行业板块定位：名称精确 → 评分模糊匹配（复用东财评分，低于阈值不匹配）。"""
    names = df["板块"].astype(str).str.strip()
    name = s.name.strip()
    hit = df[names == name]
    if not hit.empty:
        return hit
    scores = names.map(lambda ths: _industry_score(name, ths))
    best = scores.max() if not scores.empty else 0
    if best < _MIN_INDUSTRY_SCORE:
        return df.iloc[0:0]
    return df[scores == best].head(1)

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
    _to_float,
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
        # 种子行业名 → 同花顺内置板块名（精确/模糊匹配），无对应板块直接返回空，
        # 避免 akshare 内部 code_map[symbol] 抛 KeyError（如"半导体设备"不在 ths 板块表）
        ths_symbol = self._resolve_board_name(symbol)
        if ths_symbol is None:
            logger.info("[ths] 板块 %s 无同花顺对应板块，跳过日K", symbol)
            return []
        df = self._call(
            self._ak.stock_board_industry_index_ths,
            symbol=ths_symbol,
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

    def _resolve_board_name(self, symbol: str) -> str | None:
        """种子行业名 → 同花顺内置板块名：精确命中 > 评分模糊匹配（阈值复用东财 _MIN_INDUSTRY_SCORE）。

        板块表拉取失败（空）时保守回退原名；确无对应板块返回 None（调用方跳过，不触发 akshare KeyError）。
        """
        board = self._board_map()
        names = list(board.keys())
        if not names:
            return symbol
        symbol = symbol.strip()
        if symbol in names:
            return symbol
        best: str | None = None
        best_score = _MIN_INDUSTRY_SCORE
        for n in names:
            score = _industry_score(symbol, n)
            if score > best_score:
                best, best_score = n, score
        return best

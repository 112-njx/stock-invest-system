"""东方财富行情提供器（基于 akshare）：K线 / 行业指数 code 回填。

借鉴 TradingAgents-CN akshare 提供器：curl_cffi 模拟浏览器 TLS 指纹 + 请求间隔，
规避东方财富反爬断连；统一超时、指数退避重试、数据清洗。
"""

import logging
import re
import time
from datetime import UTC, datetime

import pandas as pd

from app.core.config import get_settings

from .base import (
    BaseDataProvider,
    KlineBar,
    _to_float,
)
from .em_utils import install_requests_patch

logger = logging.getLogger(__name__)

# 周期映射
_DAILY_PERIOD = {"1d": "daily", "1w": "weekly", "1mon": "monthly"}
_BOARD_PERIOD = {"1d": "日k", "1w": "周k", "1mon": "月k"}
_MIN_PERIODS = ("15m",)
# 行业板块名匹配：分类后缀（东财三级行业带罗马数字）与最低置信阈值
_ROMAN_SUFFIX = re.compile(r"[ⅠⅡⅢⅣⅤ]+$")
_MIN_INDUSTRY_SCORE = 75


def _pick_col(df: pd.DataFrame, *names: str) -> str | None:
    """返回 df 中第一个存在的列名（兼容 akshare 中英文列名，如 code/代码、name/名称）。"""
    for n in names:
        if n in df.columns:
            return n
    return None


class EastMoneyProvider(BaseDataProvider):
    name = "eastmoney"

    def can_fetch_kline(self, asset_type: str, period: str) -> bool:
        return asset_type in {"stock", "etf", "index", "industry_index"} and period in ("15m", "1d", "1w", "1mon")

    def __init__(self) -> None:
        super().__init__()
        install_requests_patch()
        import akshare as ak

        self._ak = ak
        self._board_map_cache: tuple[float, dict[str, str]] | None = None  # (ts, {名称: 板块代码})
        self._board_map_ttl = 3600  # 秒

    # ---- K线 ----
    def fetch_kline(
        self,
        symbol: str,
        period: str,
        start: datetime,
        end: datetime,
        asset_type: str = "stock",
    ) -> list[KlineBar]:
        if not self.can_fetch_kline(asset_type, period):
            return []
        if period in _MIN_PERIODS:
            return self._fetch_min_kline(symbol, start, end, asset_type)
        return self._fetch_daily_kline(symbol, period, start, end, asset_type)

    def _fetch_daily_kline(self, symbol, period, start, end, asset_type) -> list[KlineBar]:
        bars: list[KlineBar] = []
        args = self._daily_args(asset_type, symbol, period, start, end)
        if args is None:
            return bars
        df = self._call(args.pop("fn"), raise_on_giveup=True, **args)
        if df is None or df.empty:
            return bars
        for _, row in df.iterrows():
            bar = _row_to_daily_bar(row)
            if bar is not None:
                bars.append(bar)
        return bars

    def _daily_args(self, asset_type, symbol, period, start, end) -> dict | None:
        sdf, edf = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
        ak = self._ak
        if asset_type == "stock":
            return {
                "fn": ak.stock_zh_a_hist,
                "symbol": symbol,
                "period": _DAILY_PERIOD[period],
                "start_date": sdf,
                "end_date": edf,
                "adjust": "qfq",
            }
        if asset_type == "etf":
            return {
                "fn": ak.fund_etf_hist_em,
                "symbol": symbol,
                "period": _DAILY_PERIOD[period],
                "start_date": sdf,
                "end_date": edf,
                "adjust": "qfq",
            }
        if asset_type == "index":
            return {
                "fn": ak.index_zh_a_hist,
                "symbol": symbol,
                "period": _DAILY_PERIOD[period],
                "start_date": sdf,
                "end_date": edf,
            }
        if asset_type == "industry_index":  # symbol 传板块名称
            return {
                "fn": ak.stock_board_industry_hist_em,
                "symbol": symbol,
                "period": _BOARD_PERIOD[period],
                "start_date": sdf,
                "end_date": edf,
            }
        logger.warning("[eastmoney] unknown asset_type=%s", asset_type)
        return None

    def _fetch_min_kline(self, symbol, start, end, asset_type) -> list[KlineBar]:
        bars: list[KlineBar] = []
        ak = self._ak
        sdf, edf = start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")
        args = {
            "symbol": symbol,
            "period": "15",
            "start_date": sdf,
            "end_date": edf,
        }
        if asset_type == "stock":
            fn = ak.stock_zh_a_hist_min_em
            args["adjust"] = "qfq"
        elif asset_type == "etf":
            fn = ak.fund_etf_hist_min_em
            args["adjust"] = "qfq"
        elif asset_type == "index":
            fn = ak.index_zh_a_hist_min_em
        elif asset_type == "industry_index":
            fn = ak.stock_board_industry_hist_min_em
            # akshare 1.18.x 该接口签名仅 (symbol, period)，不接受 start_date/end_date/adjust，
            # 传入会抛 unexpected keyword argument；移除后返回近期全量分钟数据，由下方 start<=ts<=end 过滤。
            args.pop("start_date", None)
            args.pop("end_date", None)
        else:
            logger.warning("[eastmoney] unknown asset_type=%s", asset_type)
            return bars
        df = self._call(fn, raise_on_giveup=True, **args)
        if df is None or df.empty:
            return bars
        for _, row in df.iterrows():
            bar = _row_to_min_bar(row)
            if bar is not None and start <= bar.ts <= end:
                bars.append(bar)
        return bars

    # ---- 实时快照 ----


    # ---- 指数 PE（乐咕乐股，best-effort）----

    # ---- 全量目录 / 外部搜索（V0.2 阶段三）----
    def fetch_catalog(self) -> dict:
        """全A股代码名称 + ETF 列表（akshare），供目录预同步。"""
        stocks: list[tuple[str, str]] = []
        df = self._call(self._ak.stock_info_a_code_name, raise_on_giveup=True)
        if df is not None and not df.empty:
            code_col = _pick_col(df, "code", "代码")
            name_col = _pick_col(df, "name", "名称")
            if code_col and name_col:
                for _, row in df.iterrows():
                    stocks.append((str(row[code_col]).strip(), str(row[name_col]).strip()))
        etfs: list[tuple[str, str]] = []
        df2 = self._call(self._ak.fund_etf_spot_em, raise_on_giveup=True)
        if df2 is not None and not df2.empty:
            code_col2 = _pick_col(df2, "代码", "code")
            name_col2 = _pick_col(df2, "名称", "name")
            if code_col2 and name_col2:
                for _, row in df2.iterrows():
                    etfs.append((str(row[code_col2]).strip(), str(row[name_col2]).strip()))
        return {"stocks": stocks, "etfs": etfs}

    def search_ak_stock(self, keyword: str, limit: int = 10) -> list[tuple[str, str]]:
        """外部回退：akshare 全A股实时过滤代码/名称，命中返回 (code, name)。"""
        df = self._call(self._ak.stock_info_a_code_name, raise_on_giveup=True)
        if df is None or df.empty:
            return []
        code_col = _pick_col(df, "code", "代码")
        name_col = _pick_col(df, "name", "名称")
        if code_col is None or name_col is None:
            return []
        mask = df[code_col].astype(str).str.contains(keyword, regex=False) | df[name_col].astype(str).str.contains(
            keyword, regex=False
        )
        return [(str(r[code_col]).strip(), str(r[name_col]).strip()) for _, r in df[mask].head(limit).iterrows()]

    # ---- 行业指数 code 回填 ----
    def resolve_index_code(self, name: str) -> str | None:
        """行业名称 → 东财板块代码（BKxxxx）：先精确，后评分模糊匹配（与实时快照同套逻辑）。"""
        board_map = self._board_map()
        if not board_map:
            return None
        if name in board_map:
            return board_map[name]
        best_code: str | None = None
        best_score = _MIN_INDUSTRY_SCORE
        for em, code in board_map.items():
            score = _industry_score(name, em)
            if score > best_score:
                best_score, best_code = score, code
        return best_code

    def _board_map(self) -> dict[str, str]:
        now = time.time()
        if self._board_map_cache and now - self._board_map_cache[0] < self._board_map_ttl:
            return self._board_map_cache[1]
        ak = self._ak
        df = self._call(ak.stock_board_industry_name_em)
        mapping: dict[str, str] = {}
        if df is not None and not df.empty and "板块名称" in df.columns:
            for _, row in df.iterrows():
                mapping[str(row["板块名称"]).strip()] = str(row["板块代码"]).strip()
        self._board_map_cache = (now, mapping)
        return mapping


# ---- 数据清洗 / 转换 ----
def _row_to_daily_bar(row: pd.Series) -> KlineBar | None:
    try:
        ts = pd.to_datetime(row["日期"])
        o, h, low, c = _clean_ohlc(row)
        if o is None:
            return None
        vol = _to_float(row.get("成交量")) or 0.0
        amount = _to_float(row.get("成交额")) or 0.0
        return KlineBar(
            ts=ts.to_pydatetime().replace(tzinfo=UTC),
            open=o,
            high=h,
            low=low,
            close=c,
            volume=int(vol),
            amount=amount,
        )
    except Exception:  # noqa: BLE001
        return None


def _row_to_min_bar(row: pd.Series) -> KlineBar | None:
    try:
        ts = pd.to_datetime(row["时间"] if "时间" in row.index else row["日期"])
        o, h, low, c = _clean_ohlc(row)
        if o is None:
            return None
        vol = _to_float(row.get("成交量")) or 0.0
        amount = _to_float(row.get("成交额")) or 0.0
        tz = get_settings().tz
        return KlineBar(
            ts=ts.to_pydatetime().replace(tzinfo=None).replace(tzinfo=tz).astimezone(UTC),
            open=o,
            high=h,
            low=low,
            close=c,
            volume=int(vol),
            amount=amount,
        )
    except Exception:  # noqa: BLE001
        return None


def _clean_ohlc(row: pd.Series) -> tuple[float | None, float, float, float]:
    """提取并清洗 OHLC：空值/异常价/高低矛盾一律返回 None 剔除。"""
    try:
        o, h, low, c = (float(row["开盘"]), float(row["最高"]), float(row["最低"]), float(row["收盘"]))
    except (KeyError, TypeError, ValueError):
        return None, 0, 0, 0
    vals = (o, h, low, c)
    if any(v is None or v != v or v <= 0 for v in vals):  # NaN 与 <=0 剔除
        return None, 0, 0, 0
    if h < low or h < max(o, c) or low > min(o, c):  # 高低价矛盾剔除
        return None, 0, 0, 0
    return o, h, low, c


def _industry_score(name: str, em_name: str) -> int:
    """行业板块名相似度评分（通用模糊匹配，不硬编码具体名称，数据源可扩展）。

    规则：精确相等 > 剥离罗马数字分类后缀（Ⅲ/Ⅱ）后相等 > 前后缀包含（长度差≤3，允许"加工/概念/及服务"等修饰）>
    否定词（"非"开头，如"非白酒"）强惩罚 → 低置信度宁可不匹配（返回 None 显示 "--"）。
    """
    name, em_name = name.strip(), em_name.strip()
    if not name or not em_name:
        return 0
    if name == em_name:
        return 100
    base = _ROMAN_SUFFIX.sub("", em_name)
    if name == base:
        return 95
    # 2 字短词（消费/军工/汽车等）前缀匹配极易误配（消费→消费电子、汽车→汽车整车），仅允许精确/去后缀匹配
    shorter, longer = (name, base) if len(name) <= len(base) else (base, name)
    if longer.startswith(shorter) and len(longer) - len(shorter) <= 3 and len(shorter) >= 3:
        score = 80  # 前后缀包含（如 煤炭开采加工↔煤炭开采、油气开采及服务↔油气开采Ⅲ）
    elif shorter in longer or longer in shorter:
        score = 60  # 互为子串（置信偏低，仅作为保留得分）
    else:
        score = 0
    if em_name.startswith("非"):
        score -= 40  # 否定前缀板块（非白酒/非金属）绝不匹配
    return score

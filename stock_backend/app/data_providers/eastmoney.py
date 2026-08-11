"""东方财富行情提供器（基于 akshare）：K线 / 实时快照 / 行业指数 code 回填。

借鉴 TradingAgents-CN akshare 提供器：curl_cffi 模拟浏览器 TLS 指纹 + 请求间隔，
规避东方财富反爬断连；统一超时、指数退避重试、数据清洗。
"""

import logging
import time
from datetime import UTC, datetime

import pandas as pd

from app.core.config import get_settings

from .base import BaseDataProvider, KlineBar, RealtimeQuote, RealtimeSymbol
from .em_utils import install_requests_patch

logger = logging.getLogger(__name__)

# 周期映射
_DAILY_PERIOD = {"1d": "daily", "1w": "weekly", "1mon": "monthly"}
_BOARD_PERIOD = {"1d": "日k", "1w": "周k", "1mon": "月k"}
_MIN_PERIODS = ("15m",)
# 国内指数实时分类（覆盖固定大盘指数）
_INDEX_CATEGORIES = ("上证系列指数", "深证系列指数", "中证系列指数", "沪深系列指数")


class EastMoneyProvider(BaseDataProvider):
    name = "eastmoney"

    def __init__(self) -> None:
        install_requests_patch()
        import akshare as ak

        self._ak = ak
        settings = get_settings()
        self.timeout = settings.SYNC_TIMEOUT
        self.retry_times = settings.SYNC_RETRY_TIMES
        self.retry_backoff = settings.SYNC_RETRY_BACKOFF
        self._board_map_cache: tuple[float, dict[str, str]] | None = None  # (ts, {名称: 板块代码})
        self._board_map_ttl = 3600  # 秒

    # ---- 通用调用封装 ----
    def _call(self, fn, retry_times: int | None = None, **kwargs):
        """带指数退避重试的外部调用；彻底失败返回 None（调用方降级）。

        retry_times 覆盖全局配置：实时快照类短暂数据用 1 次，避免占用 worker。
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
                    "[eastmoney] %s failed (attempt %d): %s, retry in %.1fs",
                    getattr(fn, "__name__", fn),
                    attempt + 1,
                    str(exc)[:120],
                    wait,
                )
                time.sleep(wait)
        logger.error("[eastmoney] %s give up: %s", getattr(fn, "__name__", fn), last_exc)
        return None

    # ---- K线 ----
    def fetch_kline(
        self,
        symbol: str,
        period: str,
        start: datetime,
        end: datetime,
        asset_type: str = "stock",
    ) -> list[KlineBar]:
        if period in _MIN_PERIODS:
            return self._fetch_min_kline(symbol, start, end, asset_type)
        bars = self._fetch_daily_kline(symbol, period, start, end, asset_type)
        # 东方财富指数接口反爬限流时降级新浪（仅 A 股指数日K），保证默认大盘指数行情可用
        if not bars and asset_type == "index" and period == "1d":
            bars = self._fetch_sina_index_daily(symbol, start, end)
        return bars

    def _fetch_daily_kline(self, symbol, period, start, end, asset_type) -> list[KlineBar]:
        bars: list[KlineBar] = []
        args = self._daily_args(asset_type, symbol, period, start, end)
        if args is None:
            return bars
        df = self._call(args.pop("fn"), **args)
        if df is None or df.empty:
            # 东方财富行业板块接口被限流时，降级同花顺板块指数（仅 industry_index 日K）
            if asset_type == "industry_index" and period == "1d":
                return self._fetch_ths_board_daily(symbol, start, end)
            return bars
        for _, row in df.iterrows():
            bar = _row_to_daily_bar(row)
            if bar is not None:
                bars.append(bar)
        return bars

    def _fetch_ths_board_daily(self, board_name, start, end) -> list[KlineBar]:
        """同花顺板块指数日K降级兜底（stock_board_industry_index_ths，仅 industry_index 1d）。"""
        df = self._call(
            self._ak.stock_board_industry_index_ths,
            symbol=board_name,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
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

    def _fetch_sina_index_daily(self, symbol, start, end) -> list[KlineBar]:
        """新浪指数日K降级兜底（stock_zh_index_daily 仅 A 股指数，1d）。"""
        sina_symbol = _to_sina_index(symbol)
        if not sina_symbol:
            return []
        df = self._call(self._ak.stock_zh_index_daily, symbol=sina_symbol)
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
        else:
            logger.warning("[eastmoney] unknown asset_type=%s", asset_type)
            return bars
        df = self._call(fn, **args)
        if df is None or df.empty:
            return bars
        for _, row in df.iterrows():
            bar = _row_to_min_bar(row)
            if bar is not None and start <= bar.ts <= end:
                bars.append(bar)
        return bars

    # ---- 实时快照 ----
    def fetch_realtime(self, symbols: list[RealtimeSymbol]) -> list[RealtimeQuote]:
        by_type: dict[str, list[RealtimeSymbol]] = {}
        for s in symbols:
            by_type.setdefault(s.asset_type, []).append(s)
        quotes: list[RealtimeQuote] = []
        for atype, items in by_type.items():
            quotes.extend(self._fetch_realtime_type(atype, items))
        return quotes

    def _fetch_realtime_type(self, asset_type, items: list[RealtimeSymbol]) -> list[RealtimeQuote]:
        ak = self._ak
        if asset_type == "stock":
            df = self._call(ak.stock_zh_a_spot_em, retry_times=1)
            if df is None or df.empty:
                return [_unavailable(s) for s in items]
            return [_map_spot(df, s) for s in items]
        if asset_type == "etf":
            df = self._call(ak.fund_etf_spot_em, retry_times=1)
            if df is None or df.empty:
                return [_unavailable(s) for s in items]
            return [_map_spot(df, s) for s in items]
        if asset_type == "index":
            return self._fetch_index_realtime(items)
        if asset_type == "industry_index":
            df = self._call(ak.stock_board_industry_name_em, retry_times=1)
            if df is None or df.empty:
                return [_unavailable(s) for s in items]
            return [_map_industry_spot(df, s) for s in items]
        return [_unavailable(s) for s in items]

    def _fetch_index_realtime(self, items: list[RealtimeSymbol]) -> list[RealtimeQuote]:
        ak = self._ak
        frames: list[pd.DataFrame] = []
        for category in _INDEX_CATEGORIES:
            df = self._call(ak.stock_zh_index_spot_em, symbol=category, retry_times=1)
            if df is not None and not df.empty:
                frames.append(df)
        global_df = self._call(ak.index_global_spot_em, retry_times=1)
        if global_df is not None and not global_df.empty:
            frames.append(global_df)
        if not frames:
            return [_unavailable(s) for s in items]
        merged = pd.concat(frames, ignore_index=True)
        quotes: list[RealtimeQuote] = []
        for s in items:
            q = _map_spot(merged, s, match_by_name=True)
            quotes.append(q)
        return quotes

    # ---- 行业指数 code 回填 ----
    def resolve_index_code(self, name: str) -> str | None:
        board_map = self._board_map()
        return board_map.get(name)

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
def _to_sina_index(code: str) -> str | None:
    """东方财富指数代码 → 新浪指数代码（sh/sz 前缀），非 A 股指数返回 None。"""
    if code.startswith(("399", "932")):
        return f"sz{code}"
    if code.startswith(("000", "6")):
        return f"sh{code}"
    return None


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


def _to_float(v) -> float | None:
    if v is None or pd.isna(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _unavailable(s: RealtimeSymbol) -> RealtimeQuote:
    return RealtimeQuote(code=s.code, name=s.name, asset_type=s.asset_type, available=False)


def _map_spot(df: pd.DataFrame, s: RealtimeSymbol, match_by_name: bool = False) -> RealtimeQuote:
    """在实时表中按代码/名称定位标的并映射字段。"""
    q = _unavailable(s)
    try:
        if "代码" in df.columns:
            hit = df[df["代码"].astype(str).str.strip() == s.code.strip()]
            if hit.empty and match_by_name and "名称" in df.columns:
                hit = df[df["名称"].astype(str).str.strip() == s.name.strip()]
        else:
            hit = df[df["名称"].astype(str).str.strip() == s.name.strip()]
        if hit.empty:
            # 名称子串匹配（如 道琼斯 匹配 道琼斯指数）
            if match_by_name and "名称" in df.columns:
                hit = df[df["名称"].astype(str).str.contains(s.name[:3], regex=False)]
        if hit.empty:
            return q
        row = hit.iloc[0]
        q = RealtimeQuote(
            code=str(row.get("代码", s.code)),
            name=str(row.get("名称", s.name)),
            asset_type=s.asset_type,
            price=_to_float(row.get("最新价")) if "最新价" in row.index else None,
            change=_to_float(row.get("涨跌额")) if "涨跌额" in row.index else None,
            change_pct=_to_float(row.get("涨跌幅")) if "涨跌幅" in row.index else None,
            open=(
                _to_float(row.get("今开")) or _to_float(row.get("开盘价"))
                if "今开" in row.index or "开盘价" in row.index
                else None
            ),
            high=(
                _to_float(row.get("最高")) or _to_float(row.get("最高价"))
                if "最高" in row.index or "最高价" in row.index
                else None
            ),
            low=(
                _to_float(row.get("最低")) or _to_float(row.get("最低价"))
                if "最低" in row.index or "最低价" in row.index
                else None
            ),
            pre_close=(
                _to_float(row.get("昨收")) or _to_float(row.get("昨收价"))
                if "昨收" in row.index or "昨收价" in row.index
                else None
            ),
            volume=int(_to_float(row.get("成交量")) or 0) if "成交量" in row.index else None,
            amount=_to_float(row.get("成交额")) if "成交额" in row.index else None,
            turnover=_to_float(row.get("换手率")) if "换手率" in row.index else None,
            amplitude=_to_float(row.get("振幅")) if "振幅" in row.index else None,
            available=True,
        )
        q.updated_at = _parse_quote_time(row)
        return q
    except Exception:  # noqa: BLE001
        return q


def _map_industry_spot(df: pd.DataFrame, s: RealtimeSymbol) -> RealtimeQuote:
    q = _unavailable(s)
    try:
        hit = df[df["板块名称"].astype(str).str.strip() == s.name.strip()]
        if hit.empty:
            return q
        row = hit.iloc[0]
        return RealtimeQuote(
            code=str(row.get("板块代码", s.code)),
            name=s.name,
            asset_type=s.asset_type,
            price=_to_float(row.get("最新价")),
            change=_to_float(row.get("涨跌额")),
            change_pct=_to_float(row.get("涨跌幅")),
            turnover=_to_float(row.get("换手率")),
            available=True,
        )
    except Exception:  # noqa: BLE001
        return q


def _parse_quote_time(row: pd.Series) -> datetime | None:
    for key in ("最新行情时间", "更新时间", "时间"):
        if key in row.index:
            v = row[key]
            try:
                return pd.to_datetime(v).to_pydatetime()
            except Exception:  # noqa: BLE001
                return None
    return None

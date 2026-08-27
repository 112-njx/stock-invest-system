"""东方财富行情提供器（基于 akshare）：K线 / 实时快照 / 行业指数 code 回填。

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
    ProviderError,
    RealtimeQuote,
    RealtimeSymbol,
    _to_float,
    unavailable_quote,
)
from .em_utils import install_requests_patch

logger = logging.getLogger(__name__)

# 周期映射
_DAILY_PERIOD = {"1d": "daily", "1w": "weekly", "1mon": "monthly"}
_BOARD_PERIOD = {"1d": "日k", "1w": "周k", "1mon": "月k"}
_MIN_PERIODS = ("15m",)
# 国内指数实时分类（覆盖固定大盘指数）
_INDEX_CATEGORIES = ("上证系列指数", "深证系列指数", "中证系列指数", "沪深系列指数")
# 乐咕乐股 stock_index_pe_lg 可覆盖的固定大盘指数（其余指数/海外指数无 PE 数据源，留空显示 "--"）
_INDEX_PE_SOURCE = {"沪深300", "上证50", "中证1000"}
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
            df = self._call(ak.stock_zh_a_spot_em, retry_times=1, raise_on_giveup=True)
            if df is None or df.empty:
                return [unavailable_quote(s) for s in items]
            return [_map_spot(df, s) for s in items]
        if asset_type == "etf":
            df = self._call(ak.fund_etf_spot_em, retry_times=1, raise_on_giveup=True)
            if df is None or df.empty:
                return [unavailable_quote(s) for s in items]
            return [_map_spot(df, s) for s in items]
        if asset_type == "index":
            return self._fetch_index_realtime(items)
        if asset_type == "industry_index":
            # 板块实时接口偶发限流，retry 提升至 2 保证最新价/涨跌幅可获取
            df = self._call(ak.stock_board_industry_name_em, retry_times=2, raise_on_giveup=True)
            if df is None or df.empty:
                return [unavailable_quote(s) for s in items]
            return [_map_industry_spot(df, s) for s in items]
        return [unavailable_quote(s) for s in items]

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
            # 全部分类失败视为 Provider 级故障（供工厂熔断识别），而非单纯"无数据"
            raise ProviderError("index realtime all categories failed")
        merged = pd.concat(frames, ignore_index=True)
        quotes: list[RealtimeQuote] = []
        for s in items:
            q = _map_spot(merged, s, match_by_name=True)
            quotes.append(q)
        return quotes

    # ---- 指数 PE（乐咕乐股，best-effort）----
    def fetch_index_pe(self, names: list[str]) -> dict[str, float | None]:
        """固定大盘指数最新 PE（仅乐咕可覆盖的 A 股指数，其余返回 None 留空）。

        取最新交易日"滚动市盈率"；外部源失败/无数据返回 None，不阻塞实时轮询主链路。
        """
        result: dict[str, float | None] = {}
        for name in names:
            if name not in _INDEX_PE_SOURCE:
                result[name] = None
                continue
            try:
                df = self._call(self._ak.stock_index_pe_lg, symbol=name)
                pe: float | None = None
                if df is not None and not df.empty:
                    df = df.sort_values("日期", ascending=False)
                    for _, row in df.iterrows():
                        v = _to_float(row.get("滚动市盈率"))
                        if v is not None:
                            pe = v
                            break
                result[name] = pe
                logger.info("index_pe %s -> %s", name, pe)
            except Exception:  # noqa: BLE001
                logger.warning("index_pe %s failed (best-effort skip)", name)
                result[name] = None
        return result

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


def _map_spot(df: pd.DataFrame, s: RealtimeSymbol, match_by_name: bool = False) -> RealtimeQuote:
    """在实时表中按代码/名称定位标的并映射字段。"""
    q = unavailable_quote(s)
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
        # 特殊字段提取（个股总市值/PE、ETF 净值/溢价），供同步层写入 stock_fundamentals/etf_premiums
        if s.asset_type == "stock":
            q.extra["market_cap"] = _to_float(row.get("总市值")) if "总市值" in row.index else None
            q.extra["pe"] = _to_float(row.get("市盈率-动态")) if "市盈率-动态" in row.index else None
        elif s.asset_type == "etf":
            q.extra["nav"] = _to_float(row.get("IOPV实时估值")) if "IOPV实时估值" in row.index else None
            _disc = _to_float(row.get("基金折价率")) if "基金折价率" in row.index else None
            q.extra["premium"] = -_disc if _disc is not None else None  # 溢价率 = -折价率
        return q
    except Exception:  # noqa: BLE001
        return q


def _map_industry_spot(df: pd.DataFrame, s: RealtimeSymbol) -> RealtimeQuote:
    q = unavailable_quote(s)
    try:
        hit = _match_industry_row(df, s)
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


def _match_industry_row(df: pd.DataFrame, s: RealtimeSymbol) -> pd.DataFrame:
    """行业板块定位：板块代码（BKxxxx）精确 → 名称精确 → 评分模糊匹配（全部候选取最高分，低于阈值不匹配）。

    种子行业名称与数据源板块名可能不一致（粒度/后缀差异），但不可硬编码映射（数据源可能扩展），
    故用通用评分匹配；语义差异大且无对应板块的行业（如"创新药"）诚实返回空 → 前端显示 "--"。
    """
    if "板块代码" in df.columns and s.code:
        hit = df[df["板块代码"].astype(str).str.strip() == s.code.strip()]
        if not hit.empty:
            return hit
    if "板块名称" not in df.columns:
        return df.iloc[0:0]
    name = s.name.strip()
    hit = df[df["板块名称"].astype(str).str.strip() == name]
    if not hit.empty:
        return hit
    scores = df["板块名称"].astype(str).str.strip().map(lambda em: _industry_score(name, em))
    best = scores.max() if not scores.empty else 0
    if best < _MIN_INDUSTRY_SCORE:
        return df.iloc[0:0]
    return df[scores == best].head(1)


def _parse_quote_time(row: pd.Series) -> datetime | None:
    for key in ("最新行情时间", "更新时间", "时间"):
        if key in row.index:
            v = row[key]
            try:
                return pd.to_datetime(v).to_pydatetime()
            except Exception:  # noqa: BLE001
                return None
    return None

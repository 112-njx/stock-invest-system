"""AkShare fetcher for A-share / index / LOF daily K-line.

Concurrency guard: AkShare has no built-in rate limiter — the upstream
data source (eastmoney / sina) tolerates ~5-8 concurrent requests per
IP before returning empty frames or short-lived 4xx. We cap in-process
concurrency with a module-level Semaphore. When Spring Boot becomes
the orchestration hub (phase 4), swap this for a Redis token bucket.
"""

import os
import threading
import time
from datetime import date

import akshare as ak
import pandas as pd

from src.common.errors import AkshareUpstreamError, NoDataError
from src.common.logger import get_logger
from src.common.models import SymbolType
from src.common.retry import akshare_retry
from src.common.symbol_utils import parse_symbol

log = get_logger("fetcher")

_MAX_CONCURRENCY = max(1, min(8, int(os.getenv("AKSHARE_MAX_CONCURRENCY", "6"))))
_AK_SEMAPHORE = threading.Semaphore(_MAX_CONCURRENCY)


@akshare_retry
def _call_ak(func, **kwargs) -> pd.DataFrame:
    acquired = _AK_SEMAPHORE.acquire(timeout=60)
    if not acquired:
        raise AkshareUpstreamError(
            f"{func.__name__} timed out waiting for AkShare semaphore (>60s)"
        )
    try:
        return func(**kwargs)
    except Exception as ex:
        raise AkshareUpstreamError(f"{func.__name__} failed: {ex}") from ex
    finally:
        _AK_SEMAPHORE.release()


def fetch_a_stock_daily(
    code: str,
    start_date: date,
    end_date: date,
    adjust_type: str,
) -> pd.DataFrame:
    adjust = "" if adjust_type == "none" else adjust_type
    return _call_ak(
        ak.stock_zh_a_hist,
        symbol=code,
        period="daily",
        start_date=start_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
        adjust=adjust,
    )


def fetch_index_daily(
    market_prefix: str,
    code: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    full_symbol = f"{market_prefix}{code}"
    df = _call_ak(ak.stock_zh_index_daily_em, symbol=full_symbol)
    if df is None or df.empty:
        return df
    if "date" in df.columns:
        df = df[(df["date"] >= start_date.strftime("%Y-%m-%d"))
                & (df["date"] <= end_date.strftime("%Y-%m-%d"))]
    return df


def fetch_lof_daily(
    code: str,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    return _call_ak(
        ak.fund_lof_hist_em,
        symbol=code,
        period="daily",
        start_date=start_date.strftime("%Y%m%d"),
        end_date=end_date.strftime("%Y%m%d"),
        adjust="",
    )


def fetch(
    symbol: str,
    start_date: date,
    end_date: date,
    adjust_type: str = "qfq",
) -> tuple[pd.DataFrame, SymbolType]:
    """Dispatch by symbol type, return (dataframe, symbol_type).

    Raises NoDataError when AkShare returns an empty frame.
    """
    symbol_type, prefix, code = parse_symbol(symbol)
    stage_log = log.bind(symbol=symbol, stage="FETCH_START")
    stage_log.info(f"type={symbol_type.value} range={start_date}~{end_date} adjust={adjust_type}")

    t0 = time.perf_counter()
    if symbol_type == SymbolType.A_STOCK:
        df = fetch_a_stock_daily(code, start_date, end_date, adjust_type)
    elif symbol_type == SymbolType.INDEX:
        df = fetch_index_daily(prefix, code, start_date, end_date)
    else:
        df = fetch_lof_daily(code, start_date, end_date)

    elapsed = int((time.perf_counter() - t0) * 1000)
    rows = 0 if df is None else len(df)
    log.bind(symbol=symbol, stage="FETCH_END", latency_ms=elapsed).info(
        f"type={symbol_type.value} rows={rows}"
    )

    if df is None or df.empty:
        raise NoDataError(f"AkShare returned no rows for {symbol}")

    return df, symbol_type

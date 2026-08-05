"""Transform AkShare DataFrame → unified DailyKLine list."""

from datetime import date, datetime
from typing import List

import pandas as pd

from src.common.errors import TransformError
from src.common.logger import get_logger
from src.common.models import DailyKLine, SymbolType

log = get_logger("transformer")


_A_STOCK_MAP = {
    "日期": "trade_date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "turnover",
}

_LOF_MAP = _A_STOCK_MAP

_INDEX_MAP = {
    "date": "trade_date",
    "open": "open",
    "close": "close",
    "high": "high",
    "low": "low",
    "volume": "volume",
    "amount": "turnover",
}


def _to_date(v) -> date:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, pd.Timestamp):
        return v.date()
    if isinstance(v, str):
        return date.fromisoformat(v[:10])
    raise TransformError(f"cannot coerce trade_date value: {v!r}")


def _apply_mapping(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    missing = [k for k in mapping if k not in df.columns]
    if missing:
        raise TransformError(f"missing columns from AkShare: {missing}")
    renamed = df.rename(columns=mapping)
    return renamed[list(mapping.values())].copy()


def _build_records(
    df: pd.DataFrame,
    symbol: str,
    adjust_type: str,
    has_turnover: bool,
) -> List[DailyKLine]:
    df = df.dropna(subset=["trade_date", "open", "close", "high", "low"])
    records: List[DailyKLine] = []
    for _, row in df.iterrows():
        try:
            records.append(
                DailyKLine(
                    symbol=symbol,
                    trade_date=_to_date(row["trade_date"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]) if pd.notna(row.get("volume")) else 0,
                    turnover=float(row["turnover"]) if has_turnover and pd.notna(row.get("turnover")) else 0.0,
                    source="akshare",
                    adjust_type=adjust_type,
                )
            )
        except (TypeError, ValueError) as ex:
            raise TransformError(f"row cast failed for {symbol}: {ex}") from ex
    records.sort(key=lambda r: r.trade_date)
    return records


def transform_a_stock(df: pd.DataFrame, symbol: str, adjust_type: str) -> List[DailyKLine]:
    mapped = _apply_mapping(df, _A_STOCK_MAP)
    return _build_records(mapped, symbol, adjust_type, has_turnover=True)


def transform_index(df: pd.DataFrame, symbol: str) -> List[DailyKLine]:
    if "amount" not in df.columns:
        log.bind(symbol=symbol, stage="TRANSFORM").warning("index frame missing 'amount', filling 0")
        df = df.copy()
        df["amount"] = 0
    mapped = _apply_mapping(df, _INDEX_MAP)
    return _build_records(mapped, symbol, adjust_type="none", has_turnover=True)


def transform_lof(df: pd.DataFrame, symbol: str) -> List[DailyKLine]:
    mapped = _apply_mapping(df, _LOF_MAP)
    return _build_records(mapped, symbol, adjust_type="none", has_turnover=True)


def transform(
    df: pd.DataFrame,
    symbol: str,
    symbol_type: SymbolType,
    adjust_type: str,
) -> List[DailyKLine]:
    if symbol_type == SymbolType.A_STOCK:
        return transform_a_stock(df, symbol, adjust_type)
    if symbol_type == SymbolType.INDEX:
        return transform_index(df, symbol)
    if symbol_type == SymbolType.LOF_FUND:
        return transform_lof(df, symbol)
    raise TransformError(f"unsupported symbol_type: {symbol_type}")


def validate_and_sort(records: List[DailyKLine]) -> List[DailyKLine]:
    """Legacy helper kept for backward compat with existing tests."""
    valid = [r for r in records if r.symbol and r.trade_date and r.open is not None]
    valid.sort(key=lambda r: r.trade_date)
    return valid

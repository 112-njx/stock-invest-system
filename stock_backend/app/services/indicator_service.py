"""技术指标服务：拉取 K 线 → 计算指标 → Redis 缓存（key 含 K 线最新 ts，新数据到达自动失效）。

借鉴 TradingAgents-CN 指标统一接口 + 增量失效思路：缓存命中直接返回，失效回源重算。
"""

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.models.kline import KLINE_MODELS
from app.repositories import kline_repo
from app.services import market_service
from app.services.indicators import INDICATORS, get_indicator
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
settings = get_settings()

_DEFAULT_BACK_DAYS = 365
INDICATOR_NAMES = set(INDICATORS.keys())


def compute_indicators(
    db,
    symbol: str,
    period: str,
    names: list[str],
    params: dict | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 1000,
) -> list[dict]:
    """返回指标序列：每行含 K 线基础字段 + 指标列（ts 升序，NaN 已置 None）。"""
    if period not in KLINE_MODELS:
        raise ValueError(f"unsupported period: {period}")
    names = list(dict.fromkeys(n.strip().lower() for n in names if n.strip()))
    if not names:
        raise ValueError("names 不能为空")
    for n in names:
        if n not in INDICATOR_NAMES:
            raise ValueError(f"unsupported indicator: {n}")

    symbol_id = market_service.resolve_symbol_id(db, symbol)
    if symbol_id is None:
        return []
    if end is None:
        end = datetime.now(UTC)
    if start is None:
        start = end - timedelta(days=_DEFAULT_BACK_DAYS)

    bars = kline_repo.get_bars(db, period, symbol_id, start, end, limit=limit, offset=0)
    if not bars:
        return []

    latest_ts = bars[-1].ts
    key = _cache_key(symbol_id, period, names, params, start, end, limit, latest_ts)
    cached = _get_cache(key)
    if cached is not None:
        return cached

    df = _bars_to_df(bars)
    for name in names:
        df = get_indicator(name, (params or {}).get(name)).calculate(df)
    rows = _df_to_rows(df)
    _set_cache(key, rows)
    return rows


def _cache_key(
    symbol_id: int,
    period: str,
    names: list[str],
    params: dict | None,
    start: datetime,
    end: datetime,
    limit: int,
    latest_ts: datetime,
) -> str:
    params_hash = hashlib.md5(json.dumps(params or {}, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    names_sorted = ",".join(sorted(names))
    return (
        f"indicator:{symbol_id}:{period}:{names_sorted}:{params_hash}:"
        f"{start.isoformat()}:{end.isoformat()}:{limit}:{latest_ts.isoformat()}"
    )


def _get_cache(key: str) -> list[dict] | None:
    """读缓存；Redis 不可用或数据损坏时回源重算（不影响主链路）。"""
    try:
        raw = get_redis_client().get(key)
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None


def _set_cache(key: str, rows: list[dict]) -> None:
    try:
        get_redis_client().set(key, json.dumps(rows), ex=settings.INDICATOR_CACHE_TTL)
    except Exception:  # noqa: BLE001
        logger.warning("indicator cache set failed: %s", key)


def _bars_to_df(bars) -> pd.DataFrame:
    rows = [
        {
            "ts": b.ts,
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": b.volume,
            "amount": float(b.amount),
        }
        for b in bars
    ]
    return pd.DataFrame(rows)


def _df_to_rows(df: pd.DataFrame) -> list[dict]:
    """DataFrame → JSON 行：NaN→None、datetime→ISO 字符串、Decimal/NumPy 标量归一。"""
    out: list[dict] = []
    for _, row in df.iterrows():
        item: dict = {}
        for col in df.columns:
            v = row[col]
            if isinstance(v, (pd.Timestamp, datetime)):
                item[col] = v.isoformat()
            elif isinstance(v, Decimal):
                item[col] = float(v)
            elif isinstance(v, np.integer):
                item[col] = int(v)
            elif isinstance(v, (np.floating, float)):
                item[col] = None if pd.isna(v) else float(v)
            elif v is None or (isinstance(v, str) and v == ""):
                item[col] = None
            else:
                item[col] = v
        out.append(item)
    return out

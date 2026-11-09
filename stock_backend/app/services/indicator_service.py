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
from app.services.indicators import get_indicator
from app.utils import market_cache
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
settings = get_settings()

_DEFAULT_BACK_DAYS = 7300  # 默认回看窗口：约 20 年，等价"按 limit 取最近 N 根"（与 get_kline 默认区间对齐），避免历史指标缺失
from app.services.indicator_registry import REGISTRY, MAX_HISTORY_ROWS
INDICATOR_NAMES = set(REGISTRY)


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
    if period not in (*KLINE_MODELS.keys(), "1w"):
        raise ValueError(f"unsupported period: {period}")
    names = list(dict.fromkeys(n.strip().lower() for n in names if n.strip()))
    if not names:
        raise ValueError("names 不能为空")
    for n in names:
        if n not in INDICATOR_NAMES:
            raise ValueError(f"unsupported indicator: {n}")

    from app.services.indicator_registry import REGISTRY, validate_parameters
    if params is not None and (not isinstance(params, dict) or params.keys() - REGISTRY.keys()):
        raise ValueError('无效的指标参数')
    for name in names:
        validate_parameters(name, (params or {}).get(name))

    symbol_id = market_service.resolve_symbol_id(db, symbol)
    if symbol_id is None:
        return []
    if period in {'1m', '5m', '30m', '60m'}:
        from app.models.symbol import Symbol
        sym = db.get(Symbol, symbol_id)
        if sym is None or sym.type != 'stock':
            raise ValueError('新增分钟周期仅支持个股')
    explicit_range = start is not None or end is not None
    if end is None:
        end = datetime.now(UTC)
    if start is None:
        start = end - timedelta(days=_DEFAULT_BACK_DAYS)

    # Keep the bounded warmup window anchored to the newest bar for latest-N queries.
    bars = kline_repo.get_bars(db, period, symbol_id, datetime.min.replace(tzinfo=UTC), end,
                               limit=MAX_HISTORY_ROWS + 1, source_window=(start, end), latest=not explicit_range)
    if len(bars) > MAX_HISTORY_ROWS:
        raise ValueError(f"指标计算历史超过 {MAX_HISTORY_ROWS} 根上限，不能截断预热序列")
    if not bars:
        return []

    from app.services import indicator_policy, sdk_indicators
    policy = indicator_policy.read()
    latest_ts = bars[-1].ts
    key = _cache_key(symbol_id, period, names, params, latest_ts, explicit_range, start, end, limit,
                     source=bars[-1].source, engine=("pandas" if policy["pandas_enabled"] else "sdk") + ":v2:" + str(policy["revision"]))
    if "ma" in names:
        # The active candle can change without changing its timestamp.
        closes = [(b.ts.isoformat(), str(b.close)) for b in bars]
        key += ":ma-zb-v1:" + hashlib.sha256(json.dumps(closes).encode()).hexdigest()[:24]
    # A constituent can change while the current stock's last timestamp stays
    # unchanged. Composite values always consult the local SDK snapshot.
    cached = _get_cache(key) if 'zhishu' not in names else None
    if cached is not None:
        return cached

    pandas_names = [name for name in names if policy['pandas_enabled'] and 'pandas' in REGISTRY[name]['engines']]
    sdk_names = [name for name in names if name not in pandas_names]
    # Field selection and native cross signals require the SDK even when the
    # legacy pandas switch is enabled.
    controlled = [name for name in pandas_names if (params or {}).get(name, {}).get('cross') or (params or {}).get(name, {}).get('field', 'close') != 'close']
    pandas_names = [name for name in pandas_names if name not in controlled]
    sdk_names += controlled
    if pandas_names:
        df = _bars_to_df(bars)
        for name in pandas_names:
            df = get_indicator(name, (params or {}).get(name)).calculate(df)
        rows = _df_to_rows(df)
    else:
        rows = [market_cache.kline_bar_to_dict(b) for b in bars]
    regular_sdk = [name for name in sdk_names if name != 'zhishu']
    if regular_sdk:
        rows = sdk_indicators.calculate(rows, regular_sdk, params)
    if 'zhishu' in sdk_names:
        rows = sdk_indicators.calculate(rows, ['zhishu'], params, period=period)
    if explicit_range:
        rows = [row for row in rows if market_cache.as_utc(datetime.fromisoformat(row["ts"])) >= market_cache.as_utc(start)]
    else:
        rows = rows[-limit:]
    if 'zhishu' not in names:
        _set_cache(key, rows)
    return rows


def _cache_key(
    symbol_id: int,
    period: str,
    names: list[str],
    params: dict | None,
    latest_ts: datetime,
    explicit_range: bool,
    start: datetime,
    end: datetime,
    limit: int,
    source: str = 'stockdb',
    engine: str = 'pandas',
) -> str:
    """默认区间（未显式指定 start/end）按"最新N根"缓存：键只含 latest_ts，新K线到达自动失效。

    显式区间请求追加区间参数，避免不同范围结果串键（命中率主要优化默认场景）。
    """
    params_hash = hashlib.md5(json.dumps(params or {}, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]
    names_sorted = ",".join(sorted(names))
    from app.services.market_policy import read
    key = f"indicator:{symbol_id}:{period}:{engine}:{read()['revision']}:{source}:{names_sorted}:{params_hash}:{latest_ts.isoformat()}"
    key += f":limit={limit}"
    if explicit_range:
        key += f":{start.isoformat()}:{end.isoformat()}:{limit}"
    return key


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


def invalidate_indicator_cache(symbol_id: int, period: str) -> None:
    """中间补洞不改变最新时间戳，须显式清掉该标的/周期的指标缓存。"""
    try:
        redis = get_redis_client()
        for key in redis.scan_iter(match=f"indicator:{symbol_id}:{period}:*"):
            redis.delete(key)
    except Exception:  # noqa: BLE001
        logger.warning("indicator cache invalidate failed: %s:%s", symbol_id, period)


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

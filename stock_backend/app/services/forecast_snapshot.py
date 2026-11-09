"""Closed A-share daily data and resumable features for the forecast workflow."""

import hashlib
import json
import logging
import math
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.exceptions import ApiError
from app.models.symbol import Symbol
from app.repositories import kline_repo
from app.services import sdk_indicators
from app.services.indicator_registry import FORECAST_FEATURES, FORECAST_FEATURE_VERSION, MAX_FORECAST_ROWS
from app.utils.market_cache import as_utc, kline_bar_to_dict
from app.utils.redis_client import get_redis_client

SHANGHAI = ZoneInfo("Asia/Shanghai")
CLOSE = time(15)
MIN_BARS = 40
RESULT_WINDOW = 40
CACHE_TTL = 7 * 24 * 3600
logger = logging.getLogger(__name__)


def _closed_history(db, symbol_id, as_of):
    local = as_of.astimezone(SHANGHAI)
    last_possible_day = local.date() if local.time() >= CLOSE else local.date() - timedelta(days=1)
    # Daily timestamps identify the session. Fetch through the end of its local
    # date so both UTC-midnight and intraday-stamped daily records are covered.
    end = datetime.combine(last_possible_day, time.max, SHANGHAI).astimezone(UTC)
    bars = kline_repo.get_bars(
        db, "1d", symbol_id, datetime(1900, 1, 1, tzinfo=UTC), end,
        limit=MAX_FORECAST_ROWS + 1, latest=True,
    )
    if len(bars) > MAX_FORECAST_ROWS:
        raise ApiError(status_code=409, msg="日 K 线历史超过特征预热上限")
    sources = {bar.source for bar in bars}
    if len(sources) > 1 or sources - {"stockdb", "akshare"}:
        raise ApiError(status_code=409, msg="日 K 线来源不一致，无法生成预测快照")

    rows, excluded = [], 0
    previous = None
    for bar in bars:
        session = as_utc(bar.ts).astimezone(SHANGHAI).date()
        if session > last_possible_day:
            continue
        if session.weekday() >= 5 or (bar.volume == 0 and bar.amount == 0):
            # Skip non-session records and no-trade placeholders. Missing
            # sessions stay missing and do not generate synthetic candles.
            excluded += 1
            continue
        row = kline_bar_to_dict(bar)
        prices = [row[field] for field in ("open", "high", "low", "close")]
        if (not all(math.isfinite(price) for price in prices) or not math.isfinite(row["amount"])
                or row["volume"] < 0 or row["amount"] < 0 or
                not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]
                or (previous is not None and session <= previous)):
            raise ApiError(status_code=409, msg="日 K 线价格或交易日期异常，无法生成预测快照")
        row["ts"] = session.isoformat()
        rows.append(row)
        previous = session
    return rows, next(iter(sources), None), last_possible_day, excluded


def _read_checkpoint(key):
    try:
        redis = get_redis_client()
        raw = redis.get(key)
    except Exception:
        logger.debug("forecast checkpoint unavailable", exc_info=True)
        return None, None, None
    try:
        saved = json.loads(raw) if raw else None
    except ValueError:
        saved = None
    return redis, raw, saved


def _write_checkpoint(redis, key, previous, value):
    if redis is None:
        return
    # A slow request cannot overwrite a checkpoint committed by another request.
    try:
        redis.eval(
            "local current = redis.call('GET', KEYS[1]); "
            "if (current or '') == ARGV[1] then return redis.call('SETEX', KEYS[1], ARGV[2], ARGV[3]) end",
            1, key, previous or "", CACHE_TTL, json.dumps(value, allow_nan=False, separators=(",", ":")),
        )
    except Exception:
        logger.debug("could not save forecast checkpoint", exc_info=True)


def _features(rows, symbol_id, source):
    key = f"forecast:features:v{FORECAST_FEATURE_VERSION}:{symbol_id}:1d:qfq:{source}"
    redis, previous, saved = _read_checkpoint(key)
    count = saved.get("count", 0) if isinstance(saved, dict) else 0
    if not isinstance(count, int) or not 1 <= count <= len(rows):
        count = 0
    digest = hashlib.sha256(key.encode())
    prefix = None
    for index, row in enumerate(rows, 1):
        digest.update(json.dumps(row, allow_nan=False, separators=(",", ":")).encode() + b"\n")
        if index == count:
            prefix = digest.hexdigest()
    version = digest.hexdigest()
    reusable = (count and prefix == saved.get("data_version")
                and isinstance(saved.get("checkpoint"), str)
                and isinstance(saved.get("rows"), list)
                and len(saved["rows"]) == min(count, RESULT_WINDOW))
    if reusable and count == len(rows):
        return saved["rows"], version
    start = count if reusable else 0
    try:
        result = sdk_indicators.calculate(
            rows[start:], [FORECAST_FEATURES], None, period="1d", return_checkpoint=True,
            checkpoint=saved["checkpoint"] if reusable else None,
        )
    except ApiError as exc:
        # A rejected checkpoint can be rebuilt. Other upstream errors are
        # already actionable; avoid sending a second job to an unavailable SDK.
        if not reusable or getattr(exc.__cause__, "code", None) != 400:
            raise
        reusable = False
        result = sdk_indicators.calculate(rows, [FORECAST_FEATURES], None, period="1d", return_checkpoint=True)
    tail = ((saved["rows"] if reusable else []) + result["rows"])[-RESULT_WINDOW:]
    _write_checkpoint(redis, key, previous, {
        "count": len(rows), "data_version": version, "checkpoint": result["checkpoint"], "rows": tail,
    })
    return tail, version


def build_snapshot(db, code: str, *, as_of: datetime | None = None) -> dict:
    as_of = as_of or datetime.now(UTC)
    if as_of.tzinfo is None:
        raise ValueError("forecast snapshot cutoff requires a timezone")
    symbol = db.scalar(select(Symbol).where(Symbol.code == code, Symbol.type == "stock"))
    if symbol is None or symbol.market not in {"SSE", "SZSE", "BSE"}:
        raise ApiError(status_code=404, msg="未找到该 A 股股票")
    rows, source, last_possible_day, excluded = _closed_history(db, symbol.id, as_of)
    features, version = _features(rows, symbol.id, source) if rows else ([], None)
    return {
        "symbol": {"code": code, "name": symbol.name, "market": symbol.market},
        "period": "1d",
        "adjustment": "qfq",
        "as_of": as_of.astimezone(SHANGHAI).isoformat(),
        "closed_through": last_possible_day.isoformat(),
        "latest_session": rows[-1]["ts"] if rows else None,
        "source": source,
        "data_version": version,
        "feature_version": FORECAST_FEATURE_VERSION,
        "status": "ready" if len(rows) >= MIN_BARS else "insufficient_history",
        "bar_count": len(rows),
        "minimum_bars": MIN_BARS,
        "excluded_rows": excluded,
        "rows": features,
    }

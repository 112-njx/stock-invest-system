"""Verified A-share search directory. Never consult remote market providers."""

import hashlib
import json
import logging
import math
import re
from threading import Lock, Thread
from time import monotonic

from app.core.exceptions import ApiError
from app.data_providers.base import ProviderError
from app.data_providers.stockdb import StockDBProvider

logger = logging.getLogger(__name__)
_lock = Lock()
_snapshot: dict | None = None
_expires = 0.0
_stale = False
_refreshing = False
STOCK_CODE = re.compile(r"(?:00\d{4}|30\d{4}|60\d{4}|68\d{4}|920\d{3}|(?:43|83|87)\d{4})\Z")


def valid_bar(row: dict, code: str) -> bool:
    """Directory membership, equity code range, name and valid OHLC must agree."""
    if row.get("code") != code or not isinstance(row.get("name"), str) or not row["name"].strip():
        return False
    if not re.fullmatch(r"\d{8}", str(row.get("date", ""))):
        return False
    prices = [row.get(key) for key in ("open", "high", "low", "close")]
    if not all(isinstance(p, (int, float)) and not isinstance(p, bool) and math.isfinite(p) and p > 0 for p in prices):
        return False
    opening, high, low, closing = prices
    return low <= min(opening, closing) <= max(opening, closing) <= high


def build_directory(provider: StockDBProvider) -> dict:
    directory = provider.query("get", "股票代码")
    if not isinstance(directory, dict) or not directory:
        raise ProviderError("StockDB 股票目录为空")
    codes = sorted({str(code) for group in directory.values() for code in group if STOCK_CODE.fullmatch(str(code))})
    retired = set(provider.query("vals", "退市*") or [])
    latest = provider.latest_day()
    if latest is None:
        raise ProviderError("StockDB 缺少日 K 日期")
    day = latest.strftime("%Y%m%d")
    rows = provider.query("vals", "日k", k1="all:", k2=f"key:{day}")
    by_code = {row["code"]: row for row in rows if isinstance(row, dict) and "code" in row}
    items, excluded = [], []
    for code in codes:
        if code in retired:
            excluded.append({"code": code, "reason": "delisted"})
            continue
        row = by_code.get(code, {})
        if not valid_bar(row, code):
            # Suspended equities remain searchable using their last valid local session.
            history = provider.query("vals", "日k", k1=f"key:{code}", k2="all:", num=-20)
            row = next((bar for bar in reversed(history or []) if valid_bar(bar, code)), {})
        if not row:
            excluded.append({"code": code, "reason": "no_valid_daily_bar"})
            continue
        items.append({"code": code, "name": row["name"].strip(), "type": "stock",
                      "market": "SSE" if code.startswith(("60", "68")) else
                      "SZSE" if code.startswith(("00", "30")) else "BSE",
                      "latest_date": str(row["date"]), "ordinal": len(items) + 1})
    if not items:
        raise ProviderError("StockDB 没有可用的股票日 K 数据")
    version = hashlib.sha256(json.dumps(items, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]
    return {"version": version, "source": "stockdb", "latest_session": day,
            "total": len(items), "candidate_count": len(codes), "excluded": excluded, "items": items}


def _refresh_directory() -> None:
    """Build outside the state lock so existing readers never wait on StockDB."""
    global _snapshot, _expires, _stale, _refreshing
    try:
        snapshot = build_directory(StockDBProvider())
    except Exception as exc:
        logger.warning("stock search directory refresh failed: %s", exc)
        with _lock:
            _stale = True
            _expires = monotonic() + 30
            _refreshing = False
    else:
        with _lock:
            _snapshot = snapshot
            _stale = False
            _expires = monotonic() + 300
            _refreshing = False


def get_directory() -> dict:
    global _expires, _refreshing, _stale
    with _lock:
        expired = monotonic() >= _expires
        if _snapshot is not None:
            if expired and not _refreshing:
                _refreshing = True
                worker = Thread(target=_refresh_directory, name="stock-directory-refresh", daemon=True)
                try:
                    worker.start()
                except RuntimeError:
                    _refreshing = False
                    _stale = True
                    _expires = monotonic() + 30
                    logger.exception("could not start stock directory refresh")
            return {**_snapshot, "stale": _stale or expired or _refreshing}
        if _refreshing or not expired:
            raise ApiError(status_code=503, msg="本地股票目录尚未就绪，请稍后重试")
        _refreshing = True

    # Only a cold cache waits for I/O; concurrent callers return promptly above.
    _refresh_directory()
    with _lock:
        if _snapshot is None:
            raise ApiError(status_code=503, msg="无法读取本地股票目录，请确认 stockdb 已启动")
        return {**_snapshot, "stale": _stale}

"""Local RD historical replay and persistent snapshots for the swing matrix."""

import base64
import gzip
import json
import logging
import math
from bisect import bisect_right
from dataclasses import asdict
from hashlib import sha256
from threading import Event, Lock, Thread
from time import time
from uuid import uuid4

from redis.exceptions import RedisError

from app.core.config import get_settings
from app.services import stockdb_service as rd
from app.services.trend_engine import TrendState
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
_KEY = "stockdb:trend:realtime-v1:" + sha256(get_settings().STOCKDB_URL.encode()).hexdigest()[:12]
_FIELDS = "date,code,close,pre_close,volume,pct_chg"
_data: dict | None = None
_error = ""
_stage = "正在准备本地历史数据"
_lock = Lock()
_stop = Event()
_thread: Thread | None = None
_force = Event()
_wake = Event()


def _restore(suffix: str = "") -> dict | None:
    try:
        raw = get_redis_client().get(_KEY + suffix)
        if raw:
            result = json.loads(gzip.decompress(base64.b64decode(raw)))
            if result.get("schema") == 1:
                return result
    except (RedisError, ValueError, OSError, KeyError):
        logger.warning("trend persistent cache unavailable", exc_info=True)
    return None


def _build(base: rd.Snapshot, previous: dict | None, heartbeat, save_checkpoint=lambda payload: None) -> dict:
    global _stage
    dates = base.dates[-15:]
    year = dates[-1] // 10000
    # When the fifteen-day display crosses New Year, retain the preceding year's checkpoint.
    checkpoint_year = min(year, dates[0] // 10000)
    cutoff = checkpoint_year * 10000 + 101
    codes = sorted(base.stocks)
    pool_hash = sha256(",".join(codes).encode()).hexdigest()
    factors: dict[str, list] = {}
    with rd._client() as client:
        raw_factors = rd._rd(client, "get", "复权*", ap="get.cum")
        for key, cumulative in raw_factors:
            _, code, date = key.split(":")
            if code in base.stocks and cumulative and cumulative > 0:
                factors.setdefault(code, []).append((int(date), float(cumulative)))
        for values in factors.values():
            values.sort()
        old_factors = [(code, date, value) for code in codes for date, value in factors.get(code, []) if date < cutoff]
        factor_hash = sha256(json.dumps(old_factors).encode()).hexdigest()
        reusable = bool(
            previous and previous["year"] == checkpoint_year and previous["poolHash"] == pool_hash
            and previous["factorHash"] == factor_hash and time() - previous["fullBuiltAt"] < 86400
        )
        states = {code: TrendState(**previous["checkpoint"][code]) for code in codes} if reusable else {
            code: TrendState() for code in codes
        }
        checkpoint = previous["checkpoint"] if reusable else {}
        factor_dates = {code: [date for date, _ in values] for code, values in factors.items()}
        cells: dict[str, dict] = {code: {} for code in codes}
        prior_direction = {code: state.direction for code, state in states.items()}
        ranges = [(cutoff, dates[-1])] if reusable else [
            (19000101, 20001231), *((part * 10000 + 101, part * 10000 + 1231) for part in range(2001, year + 1))
        ]
        # Split the replay exactly at the checkpoint boundary, including when the display crosses New Year.
        ranges = [(start, min(end, dates[-1])) for start, end in ranges if start <= dates[-1]]
        if not reusable:
            ranges = [(a, b) for a, b in ranges if a < cutoff] + [(cutoff, dates[-1])]
        checkpoint_saved = reusable
        for index, (start, end) in enumerate(ranges):
            if not checkpoint_saved and start >= cutoff:
                checkpoint = {code: asdict(state) for code, state in states.items()}
                checkpoint_saved = True
                save_checkpoint({
                    "schema": 1, "year": checkpoint_year, "poolHash": pool_hash, "factorHash": factor_hash,
                    "checkpoint": checkpoint, "fullBuiltAt": time(),
                })
            for prefix in ("0", "3", "6", "8", "9"):
                if _stop.is_set():
                    raise InterruptedError("历史计算已停止")
                heartbeat()
                _stage = f"正在读取本地日线 {start // 10000} · {prefix} 开头（{index + 1}/{len(ranges)}）"
                batch = rd._rd(client, "vals", "日k", k1=f"qz:{prefix}",
                               k2=f"fwd:{start},{end}", ap=f"get.{_FIELDS}")
                valid = (row for row in batch if isinstance(row, (list, tuple)) and len(row) == 6
                         and row[0] and row[1] and isinstance(row[2], (int, float)) and math.isfinite(row[2]))
                for date, code, close, pre_close, volume, change in sorted(valid, key=lambda row: (row[0], row[1])):
                    if code not in states or close is None or close <= 0 or date > dates[-1]:
                        continue
                    state = states[code]
                    offset = bisect_right(factor_dates.get(code, []), date)
                    factor = factors[code][offset - 1][1] if offset else 1.0
                    change = float(change) if change is not None else (
                        (close / pre_close - 1) * 100 if pre_close else 0.0
                    )
                    # Unrounded adjusted prices preserve causal direction when future factors are appended.
                    cell = state.advance(date, float(close) * factor, float(volume or 0), change)
                    if date < dates[0]:
                        prior_direction[code] = state.direction
                    elif date in dates:
                        cells[code][str(date)] = {**cell, "preClose": pre_close or 0}
        if not checkpoint_saved:
            raise ValueError("历史检查点未建立")

    membership = {}
    industries = []
    for board in sorted(base.boards.values(), key=lambda item: item["code"]):
        if board["category"] == "申万一级":
            industries.append({"id": board["code"], "name": board["name"]})
            for code in board["symbols"]:
                membership.setdefault(code, board["code"])
    stocks = []
    breadth = [0] * len(dates)
    for code, state in states.items():
        direction = prior_direction[code]
        for i, date in enumerate(dates):
            cell = cells[code].get(str(date))
            if cell:
                direction = (cell["wave"] > 0) - (cell["wave"] < 0)
            breadth[i] += direction
        offset = bisect_right(factor_dates.get(code, []), dates[-1])
        latest_factor = factors[code][offset - 1][1] if offset else 1.0
        metrics = state.metrics(latest_factor)
        metrics["cross"] = bool(metrics["cross"] and state.date == dates[-1])
        stocks.append({
            "code": code, "name": base.stocks[code]["name"], "industry": membership.get(code, "unknown"),
            **metrics, "cells": [cells[code].get(str(date)) for date in dates],
        })
    stocks.sort(key=lambda stock: (-stock["wave"], stock["code"]))
    version = "trend-rt1-" + sha256(json.dumps([dates, industries, stocks], ensure_ascii=False,
                                             separators=(",", ":")).encode()).hexdigest()[:24]
    return {
        "schema": 1, "version": version, "sourceVersion": base.version, "dates": dates, "stocks": stocks,
        "breadth": breadth, "industries": industries, "checkpoint": checkpoint, "year": checkpoint_year,
        "poolHash": pool_hash, "factorHash": factor_hash, "builtAt": time(),
        "fullBuiltAt": previous["fullBuiltAt"] if reusable else time(),
    }


def _update() -> None:
    global _data, _error, _stage
    if not _lock.acquire(blocking=False):
        return
    redis = get_redis_client()
    token = str(uuid4())
    leased = False
    try:
        shared = _restore()
        if shared and (_data is None or shared["builtAt"] > _data["builtAt"]):
            _data = shared
        base = rd.snapshot()
        forced = _force.is_set()
        _force.clear()
        if _data and _data["sourceVersion"] == base.version and time() - _data["builtAt"] < 300 and not forced:
            return
        try:
            leased = bool(redis.set(_KEY + ":building", token, nx=True, ex=90))
            if not leased:
                return
        except RedisError:
            logger.debug("trend shared lock unavailable", exc_info=True)

        def heartbeat():
            if leased and not redis.eval(
                "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('expire',KEYS[1],90) end; return 0",
                1, _KEY + ":building", token,
            ):
                raise InterruptedError("历史计算所有权已交接")

        def persist_checkpoint(payload):
            if leased:
                encoded = base64.b64encode(gzip.compress(json.dumps(payload, separators=(",", ":")).encode())).decode()
                if not redis.eval(
                    "if redis.call('get',KEYS[1]) == ARGV[1] then "
                    "redis.call('set',KEYS[2],ARGV[2],'EX',604800); return 1 end; return 0",
                    2, _KEY + ":building", _KEY + ":checkpoint", token, encoded,
                ):
                    raise InterruptedError("历史检查点所有权已交接")

        candidate = _build(base, _data or _restore(":checkpoint"), heartbeat, persist_checkpoint)
        if leased:
            encoded = base64.b64encode(gzip.compress(json.dumps(candidate, ensure_ascii=False,
                                            separators=(",", ":")).encode())).decode()
            published = redis.eval(
                "if redis.call('get',KEYS[1]) == ARGV[1] then "
                "redis.call('set',KEYS[2],ARGV[2],'EX',604800); return 1 end; return 0",
                2, _KEY + ":building", _KEY, token, encoded,
            )
            if not published:
                return
        _data, _error, _stage = candidate, "", ""
    except Exception as exc:
        _error = str(exc)
        logger.exception("trend snapshot update failed: %s", exc)
    finally:
        if leased:
            try:
                redis.eval("if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) end; return 0",
                           1, _KEY + ":building", token)
            except RedisError:
                logger.debug("trend lock cleanup unavailable", exc_info=True)
        _lock.release()


def start() -> None:
    global _thread, _data
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _data = _data or _restore()

    def run():
        while not _stop.is_set():
            _update()
            _wake.wait(15)
            _wake.clear()

    _thread = Thread(target=run, name="stockdb-trends", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
    _wake.set()


def refresh() -> dict:
    _force.set()
    _wake.set()
    start()
    return status()


def current(version: str | None = None) -> dict:
    start()
    if _data is None:
        raise rd.StockDBError(_error or _stage)
    if version and version != _data["version"]:
        raise ValueError("波段数据版本已更新")
    return _data


def status() -> dict:
    return {"ready": _data is not None, "updating": _lock.locked(), "stage": _stage,
            "error": _error, "version": _data["version"] if _data else None}


def overview(data: dict, industry: str) -> dict:
    stocks = [stock for stock in data["stocks"] if industry == "all" or stock["industry"] == industry]
    returns = [stock["return"] for stock in stocks if stock["return"] is not None]
    counts = {}
    for stock in data["stocks"]:
        counts[stock["industry"]] = counts.get(stock["industry"], 0) + 1
    return {
        "version": data["version"], "dates": data["dates"], "breadth": data["breadth"], "industry": industry,
        "industries": [{"id": "all", "name": "全部", "count": len(data["stocks"])},
                       *[{**item, "count": counts.get(item["id"], 0)} for item in data["industries"]],
                       *([{"id": "unknown", "name": "未分类", "count": counts["unknown"]}] if counts.get("unknown") else [])],
        "stocks": [{key: stock[key] for key in ("code", "name", "wave", "return")} for stock in stocks],
        "average": sum(returns) / len(returns) if returns else None,
        "crossCount": sum(stock["cross"] for stock in stocks),
    }

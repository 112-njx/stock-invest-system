"""Read-only RD queries for the independent stockdb index workspace."""

import json
import math
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256
from threading import Lock

import httpx
import numpy as np

from app.core.config import get_settings

CATEGORIES = {"sw1": "申万一级", "sw2": "申万二级", "sw3": "申万三级", "concept": "概念"}
WEIGHTS = ("equal", "float_mv", "amount", "volume", "total_mv")
BAR_FIELDS = "date,code,name,open,high,low,close,pre_close,volume,amount,float_mv,total_mv,turnover"
# The reference page starts its trading window ten calendar weeks before the latest local session.
LOOKBACK_DAYS = 70
CACHE_SECONDS = 300


class StockDBError(Exception):
    pass


def _rd(client: httpx.Client, command: str, table: str, **params) -> list:
    import os
    if os.environ.get('STOCKDB_CONTROL_DIR'):
        from .stockdb_files import ensure_available
        try:
            ensure_available(os.environ['STOCKDB_CONTROL_DIR'])
        except RuntimeError as exc:
            raise StockDBError(str(exc)) from exc
    try:
        response = client.get("/", params={"cmd": command, "t": table, "json": 1, **params})
        response.raise_for_status()
        rows = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise StockDBError("无法读取本地 stockdb，请确认 stockdb.exe 已启动且数据已同步。") from exc
    if not isinstance(rows, list):
        raise StockDBError("本地 stockdb 返回了无法识别的数据。")
    return rows


def _client() -> httpx.Client:
    return httpx.Client(base_url=get_settings().STOCKDB_URL, timeout=25, trust_env=False)


@dataclass
class Snapshot:
    dates: list[int]
    boards: dict
    stocks: dict
    # Constituent index × session × OHLCV/amount/market cap.
    values: np.ndarray
    positions: dict
    version: str = ""
    board_cache: dict = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)

    def index(self, codes: list[str], weight: str) -> list:
        positions = [self.positions[code] for code in codes if code in self.positions]
        if not positions:
            return []
        values = self.values[positions]
        prices = values[:, :, :4]
        previous = values[:, :, 8]
        valid = (previous > 0) & np.all(prices > 0, axis=2)
        weights = np.ones_like(previous) if weight == "equal" else values[:, :, {
            "volume": 4, "amount": 5, "float_mv": 6, "total_mv": 7,
        }[weight]]
        weights = np.where(valid, weights, 0)
        totals = weights.sum(axis=0)
        relatives = np.divide(prices, previous[:, :, None], out=np.zeros_like(prices), where=valid[:, :, None])
        ratios = np.divide(
            (relatives * weights[:, :, None]).sum(axis=0),
            totals[:, None],
            out=np.ones((len(self.dates), 4)),
            where=totals[:, None] > 0,
        )
        activity = np.where(valid[:, :, None], values[:, :, 4:6], 0).sum(axis=0)
        level = 1000.0
        bars = []
        for date, ratio, (volume, amount), total in zip(self.dates, ratios, activity, totals, strict=True):
            if not total:
                continue
            previous_level = level
            level *= ratio[3]
            bars.append([date, *(round(previous_level * x, 4) for x in ratio), volume, amount, previous_level])
        # Match the stockdb indicator wrapper, which drops the first calculated period.
        return bars[1:]

    def category(self, category: str, weight: str) -> list:
        key = (category, weight)
        with self.lock:
            if key not in self.board_cache:
                self.board_cache[key] = [
                    {"id": code, "name": board["name"], "count": len(board["symbols"]),
                     "bars": self.index(board["symbols"], weight)}
                    for code, board in self.boards.items()
                    if board["category"] == CATEGORIES[category]
                ]
                if len(self.board_cache) > 6:
                    del self.board_cache[next(iter(self.board_cache))]
            return self.board_cache[key]

    def members(self, codes: list[str]) -> list:
        return [
            {"code": code, "name": self.stocks[code]["name"], "bar": self.stocks[code]["latest"],
             "metrics": self.stocks[code].get("metrics", {})}
            for code in codes if code in self.stocks
        ]


def _load_snapshot() -> Snapshot:
    digest = sha256()
    with _client() as client:
        keys = _rd(client, "keys", "日k", k1="key:600519", k2="all:")
        dates = sorted(int(key.rsplit(":", 1)[-1]) for key in keys)
        if dates:
            latest = datetime.strptime(str(dates[-1]), "%Y%m%d")
            start = int((latest - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d"))
            dates = [date for date in dates if date >= start]
        if len(dates) < 2:
            raise StockDBError("本地 stockdb 中缺少可用的日 K 数据。")
        raw_boards = _rd(client, "get", "板块*")
        digest.update(json.dumps(raw_boards, ensure_ascii=False, separators=(",", ":")).encode())
        boards = {
            board["code"]: board for _, board in raw_boards
            if board["category"] in CATEGORIES.values()
        }
        factors = defaultdict(list)
        raw_factors = _rd(client, "get", "复权*", ap="get.cum")
        digest.update(json.dumps(raw_factors, separators=(",", ":")).encode())
        for key, cumulative in raw_factors:
            _, code, date = key.split(":")
            if cumulative and cumulative > 0:
                factors[code].append((int(date), cumulative))
        rows = defaultdict(list)
        for prefix in ("0", "3", "6", "8", "9"):
            batch = _rd(client, "vals", "日k", k1=f"qz:{prefix}",
                        k2=f"fwd:{dates[0]},{dates[-1]}", ap=f"get.{BAR_FIELDS}")
            digest.update(json.dumps(batch, ensure_ascii=False, separators=(",", ":")).encode())
            for row in batch:
                if len(row) in (12, 13) and all(row[3:7]) and row[0] and row[1]:
                    rows[row[1]].append([*row, None] if len(row) == 12 else row)

    stocks = {}
    date_position = {date: i for i, date in enumerate(dates)}
    positions = {code: i for i, code in enumerate(rows)}
    values = np.zeros((len(positions), len(dates), 9))
    for code, history in rows.items():
        timeline = sorted(factors[code])
        factor_dates = [date for date, _ in timeline]
        latest_factor = timeline[-1][1] if timeline else 1
        bars = []
        latest_bar = None
        previous = 0
        metrics = {}
        for date, _, name, open_, high, low, close, pre_close, volume, amount, float_mv, total_mv, turnover in sorted(
            history, key=lambda row: row[0],
        ):
            if date not in date_position:
                continue
            offset = bisect_right(factor_dates, date)
            multiplier = (timeline[offset - 1][1] if offset else 1) / latest_factor
            adjusted = [round(price * multiplier, 2) for price in (open_, high, low, close)]
            metrics = {key: value if isinstance(value, (int, float)) and math.isfinite(value) else None
                       for key, value in {"volume": volume, "amount": amount, "float_mv": float_mv,
                                          "total_mv": total_mv, "turnover": turnover}.items()}
            volume, amount = volume or 0, amount or 0
            values[positions[code], date_position[date]] = [
                *adjusted, volume, amount, float_mv or 0, total_mv or 0, previous,
            ]
            previous = adjusted[3]
            bars.append([date, *adjusted, volume, amount, round((pre_close or 0) * multiplier, 2)])
            latest_bar = [date, open_, high, low, close, volume, amount, pre_close or 0]
            latest_name = name or code
        if latest_bar is not None:
            stocks[code] = {"name": latest_name, "latest": latest_bar, "bars": bars, "metrics": metrics}
    return Snapshot(dates, boards, stocks, values, positions, "v3-" + digest.hexdigest()[:24])


def performance(code: str, as_of: int) -> dict:
    """Read just the selected equity's last 61 sessions, without changing index inception."""
    with _client() as client:
        keys = _rd(client, "keys", "日k", k1=f"key:{code}", k2="all:")
        dates = sorted(int(key.rsplit(":", 1)[-1]) for key in keys
                       if int(key.rsplit(":", 1)[-1]) <= as_of)[-61:]
        if not dates:
            raise StockDBError("所选股票缺少历史行情。")
        # A negative num on an RD fwd range reverses its first rows, not its last rows.
        rows = _rd(client, "vals", "日k", k1=f"key:{code}", k2=f"fwd:{dates[0]},{as_of}", ap="get.date,close")
        factors = _rd(client, "get", "复权", k1=f"key:{code}", k2="all:", ap="get.cum")
    timeline = sorted((int(key.rsplit(":", 1)[-1]), cumulative) for key, cumulative in factors
                      if isinstance(cumulative, (int, float)) and math.isfinite(cumulative) and cumulative > 0)
    factor_dates = [day for day, _ in timeline]
    history = []
    for day, close in sorted(rows):
        if day > as_of or not isinstance(close, (int, float)) or not math.isfinite(close) or close <= 0:
            continue
        offset = bisect_right(factor_dates, day)
        factor = timeline[offset - 1][1] if offset else 1
        history.append((day, close * factor))
    if not history or history[-1][0] != as_of:
        raise StockDBError("所选股票的阶段行情暂不可用，请刷新后重试。")
    result = {}
    for days in (5, 20, 60):
        baseline = history[-days - 1] if len(history) > days else None
        result[str(days)] = {"value": (history[-1][1] / baseline[1] - 1) * 100 if baseline else None,
                             "start_date": baseline[0] if baseline else None, "end_date": as_of}
    return {"as_of": as_of, "returns": result}


def snapshot() -> Snapshot:
    from app.services.stockdb_cache import get_snapshot

    return get_snapshot()


def minutes(code: str, date: int) -> list:
    with _client() as client:
        rows = _rd(client, "vals", "分钟k", k1=f"key:{code}", k2=f"qz:{date}")
    return sorted(
        ([row["date"], row["open"], row["high"], row["low"], row["close"],
          row.get("volume") or 0, row.get("amount") or 0, 0] for row in rows
         if row.get("date") and all(row.get(key) for key in ("open", "high", "low", "close"))),
        key=lambda row: row[0],
    )

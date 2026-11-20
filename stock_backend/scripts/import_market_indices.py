"""Seed headline indices from the read-only QMT Parquet export.

Run from stock_backend: python -m scripts.import_market_indices E:/stock_db
Install pyarrow in the Python environment used for this one-time import.
"""

import argparse
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow.dataset as parquet

from app.repositories import market_index_repo as repo
from app.utils.db import get_session

SHANGHAI = ZoneInfo("Asia/Shanghai")
COLUMNS = ["date", "c00", "c01", "c02", "c03", "c04", "c06", "c08", "c09", "c13"]


def _ohlc(row):
    values = tuple(row[field] / 1000 for field in ("c01", "c02", "c03", "c04"))
    opening, high, low, close = values
    return values if 0 < low <= min(opening, close) <= max(opening, close) <= high else None


def _turnover(row):
    # The exported index volume is in lots (c06). The next aligned 64-bit
    # field is turnover in yuan, split into little-endian c08/c09 words.
    return row["c06"] * 100, (row["c09"] << 32) | row["c08"]


def _daily(rows):
    for row in rows:
        prices = _ohlc(row)
        if prices is None:
            continue
        stamp = datetime.strptime(str(row["date"]), "%Y%m%d").replace(tzinfo=UTC)
        volume, amount = _turnover(row)
        yield dict(zip(("open", "high", "low", "close"), prices), ts=stamp, volume=volume, amount=amount,
                   pre_close=row["c13"] / 1000 or None, source="qmt")


def _minutes(rows):
    groups = defaultdict(dict)
    for row in rows:
        stamp = datetime.fromtimestamp(row["c00"], SHANGHAI)
        if int(stamp.strftime("%Y%m%d")) != row["date"] or stamp.second or not _ohlc(row):
            continue
        minute = stamp.hour * 60 + stamp.minute
        if 570 <= minute <= 690:
            session = 570
        elif 781 <= minute <= 900:
            session = 780
        else:
            continue
        last = session + 15 * max(1, (minute - session + 14) // 15)
        groups[(stamp.date(), last)][minute] = row
    for (day, last), minutes in groups.items():
        if any(minute not in minutes for minute in range(last - 14, last + 1)):
            continue
        rows = [minutes[minute] for minute in sorted(minutes)]
        stamp = datetime(day.year, day.month, day.day, last // 60, last % 60, tzinfo=SHANGHAI)
        measures = [_turnover(row) for row in rows]
        yield dict(ts=stamp.astimezone(UTC), open=rows[0]["c01"] / 1000,
                   high=max(row["c02"] for row in rows) / 1000, low=min(row["c03"] for row in rows) / 1000,
                   close=rows[-1]["c04"] / 1000, pre_close=rows[0]["c13"] / 1000 or None,
                   volume=sum(volume for volume, _ in measures), amount=sum(amount for _, amount in measures),
                   source="qmt")


def _rows(paths, code):
    if not paths:
        return []
    dataset = parquet.dataset([str(path) for path in sorted(paths)], format="parquet")
    return dataset.to_table(filter=parquet.field("code") == code, columns=COLUMNS).to_pylist()


def run(root, *, dry_run=False):
    root = root / "qmt"
    if not all((root / table).is_dir() for table in ("daily", "minute")):
        raise ValueError(f"QMT Parquet 根目录无效: {root}")
    with get_session() as db:
        symbols = repo.symbols(db)
        if {(sym.market, sym.code) for sym in symbols} != repo.QMT_MARKETS.keys() or len(symbols) != len(repo.QMT_MARKETS):
            raise RuntimeError("请先初始化行情页 8 个固定大盘指数的证券目录")
        for sym in symbols:
            market = repo.QMT_MARKETS[sym.market, sym.code]
            daily = list(_daily(_rows(list((root / "daily" / f"market={market}").glob("year=*/data.parquet")), sym.code)))
            files = list((root / "minute" / f"market={market}").glob(f"year=*/month=*/prefix={sym.code[:4]}.parquet"))
            minute = list(_minutes(_rows(files, sym.code)))
            for period, rows in (("1d", daily), ("15m", minute)):
                added = 0 if dry_run else repo.upsert(db, sym, period, rows, initial=True)
                stamps = [row["ts"] for row in rows]
                print(sym.code, period, "validated", len(rows), "inserted", added,
                      min(stamps, default=None), max(stamps, default=None), flush=True)
            db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Path containing the qmt/ folder")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(args.root, dry_run=args.dry_run)

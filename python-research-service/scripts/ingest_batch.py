#!/usr/bin/env python
"""Batch ingest multiple symbols concurrently.

Usage:
    python scripts/ingest_batch.py --symbols sh600519,sz000001 --months 3
    python scripts/ingest_batch.py --symbols @symbols.txt --months 6 --parallel 4

Exit codes:
    0 = all succeeded
    2 = partial failure
    1 = all failed / fatal error
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import List

from dateutil.relativedelta import relativedelta

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.akshare_ingest.fetcher import fetch  # noqa: E402
from src.akshare_ingest.transformer import transform  # noqa: E402
from src.akshare_ingest.writer import write_daily_kline  # noqa: E402
from src.common.errors import IngestError  # noqa: E402
from src.common.logger import get_logger  # noqa: E402


def _parse_symbols(raw: str) -> List[str]:
    if raw.startswith("@"):
        path = Path(raw[1:])
        if not path.exists():
            raise SystemExit(f"symbols file not found: {path}")
        lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
        return [s for s in lines if s and not s.startswith("#")]
    return [s.strip() for s in raw.split(",") if s.strip()]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Batch ingest daily K-line via AkShare")
    p.add_argument("--symbols", required=True,
                   help="Comma-separated symbols, or @path/to/symbols.txt")
    p.add_argument("--months", type=int, default=3)
    p.add_argument("--start-date", dest="start_date")
    p.add_argument("--end-date", dest="end_date")
    p.add_argument("--adjust-type", dest="adjust_type", default="qfq",
                   choices=["qfq", "hfq", "none"])
    p.add_argument("--parallel", type=int, default=4)
    p.add_argument("--request-id", dest="request_id", default=None)
    return p.parse_args()


def _resolve_range(args: argparse.Namespace) -> tuple[date, date]:
    end = date.fromisoformat(args.end_date) if args.end_date else date.today()
    if args.start_date:
        start = date.fromisoformat(args.start_date)
    else:
        start = end - relativedelta(months=args.months)
    return start, end


def _ingest_one(symbol: str, start: date, end: date, adjust_type: str, request_id: str) -> dict:
    log = get_logger("ingest_batch").bind(request_id=request_id, symbol=symbol, stage="ITEM_START")
    log.info(f"range={start}~{end} adjust={adjust_type}")
    t0 = time.perf_counter()
    try:
        df, symbol_type = fetch(symbol, start, end, adjust_type)
        records = transform(df, symbol, symbol_type, adjust_type)
        result = write_daily_kline(records)
    except IngestError as ex:
        return {
            "symbol": symbol,
            "status": "FAIL",
            "errorCode": ex.error_code,
            "message": str(ex),
        }
    except Exception as ex:
        return {
            "symbol": symbol,
            "status": "FAIL",
            "errorCode": "UNEXPECTED",
            "message": f"{type(ex).__name__}: {ex}",
        }
    return {
        "symbol": symbol,
        "status": "OK",
        "rows": len(records),
        "affected": result.inserted_or_updated,
        "elapsedMs": int((time.perf_counter() - t0) * 1000),
    }


def main() -> int:
    args = _parse_args()
    request_id = args.request_id or f"batch-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6]}"

    try:
        symbols = _parse_symbols(args.symbols)
        start, end = _resolve_range(args)
    except (ValueError, SystemExit) as ex:
        sys.stdout.write(json.dumps({
            "requestId": request_id, "status": "FAIL", "errorCode": "BAD_ARGS", "message": str(ex),
        }, ensure_ascii=False) + "\n")
        return 1

    if not symbols:
        sys.stdout.write(json.dumps({
            "requestId": request_id, "status": "FAIL", "errorCode": "BAD_ARGS", "message": "no symbols",
        }, ensure_ascii=False) + "\n")
        return 1

    parallel = max(1, min(args.parallel, 8))
    log = get_logger("ingest_batch").bind(request_id=request_id, stage="BATCH_START")
    log.info(f"total={len(symbols)} parallel={parallel} range={start}~{end}")

    started = time.perf_counter()
    results: List[dict] = []
    with ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = {
            pool.submit(_ingest_one, s, start, end, args.adjust_type, request_id): s
            for s in symbols
        }
        for fut in as_completed(futures):
            results.append(fut.result())

    succeeded = [r for r in results if r["status"] == "OK"]
    failed = [r for r in results if r["status"] != "OK"]

    summary = {
        "requestId": request_id,
        "total": len(symbols),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "failedSymbols": [r["symbol"] for r in failed],
        "results": results,
        "elapsedMs": int((time.perf_counter() - started) * 1000),
    }
    sys.stdout.write(json.dumps(summary, ensure_ascii=False) + "\n")
    sys.stdout.flush()

    if failed and succeeded:
        return 2
    if failed and not succeeded:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""Ingest a single symbol's daily K-line and upsert into MySQL.

Usage:
    python scripts/ingest_single.py --symbol sh600519 --months 3
    python scripts/ingest_single.py --symbol sz000001 --start-date 2020-01-01 --end-date 2023-12-31
    python scripts/ingest_single.py --symbol sh000001 --months 1 --adjust-type none

Outputs a single-line JSON summary on stdout for Spring Boot parsing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import date, datetime
from pathlib import Path

from dateutil.relativedelta import relativedelta

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.akshare_ingest.fetcher import fetch  # noqa: E402
from src.akshare_ingest.transformer import transform  # noqa: E402
from src.akshare_ingest.writer import write_daily_kline  # noqa: E402
from src.common.errors import (  # noqa: E402
    AkshareUpstreamError,
    IngestError,
    NoDataError,
    TransformError,
    WriterError,
)
from src.common.logger import get_logger  # noqa: E402


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest single stock/index/LOF daily K-line via AkShare")
    p.add_argument("--symbol", required=True, help="e.g. sh600519 / sz000001 / sh000001")
    p.add_argument("--months", type=int, help="Look back N months from today")
    p.add_argument("--start-date", dest="start_date", help="YYYY-MM-DD")
    p.add_argument("--end-date", dest="end_date", help="YYYY-MM-DD (default: today)")
    p.add_argument(
        "--adjust-type",
        dest="adjust_type",
        default="qfq",
        choices=["qfq", "hfq", "none"],
        help="Adjust type (default qfq)",
    )
    p.add_argument("--request-id", dest="request_id", default=None)
    return p.parse_args()


def _resolve_range(args: argparse.Namespace) -> tuple[date, date]:
    end = date.fromisoformat(args.end_date) if args.end_date else date.today()
    if args.start_date:
        start = date.fromisoformat(args.start_date)
    else:
        months = args.months if args.months else 3
        start = end - relativedelta(months=months)
    if start > end:
        raise ValueError(f"start-date {start} must be <= end-date {end}")
    return start, end


def _emit(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    args = _parse_args()
    request_id = args.request_id or f"ingest-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6]}"
    log = get_logger("ingest_single").bind(request_id=request_id, symbol=args.symbol, stage="START")

    started = time.perf_counter()
    try:
        start, end = _resolve_range(args)
    except ValueError as ex:
        _emit({
            "requestId": request_id,
            "symbol": args.symbol,
            "status": "FAIL",
            "errorCode": "BAD_ARGS",
            "message": str(ex),
        })
        return 1

    log.info(f"range={start}~{end} adjust={args.adjust_type}")

    try:
        df, symbol_type = fetch(args.symbol, start, end, args.adjust_type)
        records = transform(df, args.symbol, symbol_type, args.adjust_type)
        result = write_daily_kline(records)
    except NoDataError as ex:
        _emit({
            "requestId": request_id,
            "symbol": args.symbol,
            "status": "FAIL",
            "errorCode": NoDataError.error_code,
            "message": str(ex),
        })
        return 1
    except AkshareUpstreamError as ex:
        _emit({
            "requestId": request_id,
            "symbol": args.symbol,
            "status": "FAIL",
            "errorCode": AkshareUpstreamError.error_code,
            "message": str(ex),
        })
        return 1
    except TransformError as ex:
        _emit({
            "requestId": request_id,
            "symbol": args.symbol,
            "status": "FAIL",
            "errorCode": TransformError.error_code,
            "message": str(ex),
        })
        return 1
    except WriterError as ex:
        _emit({
            "requestId": request_id,
            "symbol": args.symbol,
            "status": "FAIL",
            "errorCode": WriterError.error_code,
            "message": str(ex),
        })
        return 1
    except IngestError as ex:
        _emit({
            "requestId": request_id,
            "symbol": args.symbol,
            "status": "FAIL",
            "errorCode": ex.error_code,
            "message": str(ex),
        })
        return 1
    except Exception as ex:
        _emit({
            "requestId": request_id,
            "symbol": args.symbol,
            "status": "FAIL",
            "errorCode": "UNEXPECTED",
            "message": f"{type(ex).__name__}: {ex}",
        })
        return 1

    elapsed = int((time.perf_counter() - started) * 1000)
    _emit({
        "requestId": request_id,
        "symbol": args.symbol,
        "status": "OK",
        "rows": len(records),
        "affected": result.inserted_or_updated,
        "batches": result.batches,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "adjustType": args.adjust_type,
        "elapsedMs": elapsed,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())

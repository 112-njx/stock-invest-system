"""Batch upsert DailyKLine records into stock_daily_kline (idempotent)."""

import time
from typing import List

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from config.settings import get_settings
from src.common.errors import WriterError
from src.common.logger import get_logger
from src.common.models import DailyKLine, WriteResult
from src.common.retry import db_retry

log = get_logger("writer")

_BATCH_SIZE = 500
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().db_url, pool_pre_ping=True, pool_size=2)
    return _engine


UPSERT_SQL = text("""
INSERT INTO stock_daily_kline
    (symbol, trade_date, open_price, high_price, low_price, close_price,
     volume, turnover, source, adjust_type)
VALUES
    (:symbol, :trade_date, :open, :high, :low, :close,
     :volume, :turnover, :source, :adjust_type)
ON DUPLICATE KEY UPDATE
    open_price=VALUES(open_price),
    high_price=VALUES(high_price),
    low_price=VALUES(low_price),
    close_price=VALUES(close_price),
    volume=VALUES(volume),
    turnover=VALUES(turnover),
    source=VALUES(source),
    updated_at=CURRENT_TIMESTAMP
""")


def _to_params(r: DailyKLine) -> dict:
    return {
        "symbol": r.symbol,
        "trade_date": r.trade_date,
        "open": r.open,
        "high": r.high,
        "low": r.low,
        "close": r.close,
        "volume": r.volume,
        "turnover": r.turnover,
        "source": r.source,
        "adjust_type": r.adjust_type,
    }


@db_retry
def write_daily_kline(records: List[DailyKLine]) -> WriteResult:
    if not records:
        return WriteResult(0, 0, 0)

    symbol = records[0].symbol
    total = len(records)
    log.bind(symbol=symbol, stage="WRITE_START").info(f"rows={total} batch_size={_BATCH_SIZE}")

    t0 = time.perf_counter()
    affected = 0
    batches = 0
    engine = _get_engine()

    try:
        with engine.begin() as conn:
            for i in range(0, total, _BATCH_SIZE):
                chunk = records[i:i + _BATCH_SIZE]
                params = [_to_params(r) for r in chunk]
                result = conn.execute(UPSERT_SQL, params)
                if result.rowcount and result.rowcount > 0:
                    affected += result.rowcount
                batches += 1
    except SQLAlchemyError as ex:
        raise WriterError(f"upsert failed for {symbol}: {ex}") from ex

    elapsed = int((time.perf_counter() - t0) * 1000)
    log.bind(symbol=symbol, stage="WRITE_END", latency_ms=elapsed).info(
        f"batches={batches} affected={affected} rows={total}"
    )
    return WriteResult(inserted_or_updated=affected, batches=batches, elapsed_ms=elapsed)


def write_to_mysql(records: List[DailyKLine]) -> int:
    """Backward-compat helper preserving legacy return type."""
    return write_daily_kline(records).inserted_or_updated

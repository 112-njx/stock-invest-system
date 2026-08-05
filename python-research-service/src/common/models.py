"""Domain models for ingest pipeline."""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Tuple


class SymbolType(str, Enum):
    A_STOCK = "A_STOCK"
    INDEX = "INDEX"
    LOF_FUND = "LOF_FUND"


@dataclass
class DailyKLine:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    turnover: float
    source: str = "akshare"
    adjust_type: str = "qfq"

    def to_row(self) -> Tuple:
        return (
            self.symbol,
            self.trade_date,
            self.open,
            self.high,
            self.low,
            self.close,
            self.volume,
            self.turnover,
            self.source,
            self.adjust_type,
        )


@dataclass
class WriteResult:
    inserted_or_updated: int
    batches: int
    elapsed_ms: int

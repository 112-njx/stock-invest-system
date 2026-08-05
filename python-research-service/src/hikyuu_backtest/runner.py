"""
Hikyuu backtest adapter — placeholder for Phase 3.

This module will consume BacktestSpec JSON, execute Hikyuu strategies,
and produce BacktestResult JSON with trade details and chart annotations.
"""

import logging

logger = logging.getLogger(__name__)


def run_backtest(spec: dict) -> dict:
    """Placeholder: accept BacktestSpec, return BacktestResult."""
    logger.info("Hikyuu backtest runner called (placeholder) with spec: %s", spec)
    return {
        "status": "not_implemented",
        "message": "Hikyuu backtest runner will be implemented in Phase 3",
    }

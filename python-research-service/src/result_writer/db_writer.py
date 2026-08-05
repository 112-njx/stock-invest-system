"""
Result writer — placeholder for Phase 3.

Writes backtest results, trade details, and chart annotations to MySQL.
"""

import logging

logger = logging.getLogger(__name__)


def save_backtest_result(task_id: str, result: dict) -> None:
    """Placeholder: save backtest result to MySQL."""
    logger.info("save_backtest_result called (placeholder): task_id=%s", task_id)

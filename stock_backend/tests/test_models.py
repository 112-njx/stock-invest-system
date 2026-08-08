"""1.3 模型与迁移一致性测试。"""

from app.models import Base
from app.utils.kline_partition import KLINE_TABLES

EXPECTED_TABLES = {
    "users",
    "user_watchlist",
    "user_memory_files",
    "support_resistance",
    "symbols",
    "kline_15m",
    "kline_1d",
    "kline_1w",
    "kline_1mon",
    "snapshot_realtime",
    "stock_fundamentals",
    "etf_premiums",
    "index_valuations",
    "conversations",
    "chat_messages",
    "trading_strategies",
    "backtest_tasks",
    "backtest_results",
    "sync_tasks",
    "task_logs",
    "user_agents",
    "agent_runs",
    "agent_steps",
    "memory_chunks",
}


def test_all_tables_registered_in_metadata():
    registered = set(Base.metadata.tables.keys())
    assert EXPECTED_TABLES <= registered


def test_kline_partition_table_names():
    assert KLINE_TABLES == ("kline_15m", "kline_1d", "kline_1w", "kline_1mon")

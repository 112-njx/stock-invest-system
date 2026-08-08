"""一次性脚本：从 docs/sql 生成初始迁移 0001_initial_schema.py（内嵌 DDL）。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]  # stock-backend
SQL_01 = ROOT / "docs" / "sql" / "01_schema.sql"
SQL_03 = ROOT / "docs" / "sql" / "03_agent_extensions.sql"
OUT = Path(__file__).resolve().parent / "0001_initial_schema.py"


def load_ddl(path: Path) -> str:
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s.upper() in ("BEGIN;", "COMMIT;"):  # 事务交由 Alembic 管理
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def main() -> None:
    ddl = load_ddl(SQL_01) + "\n\n" + load_ddl(SQL_03)
    tables = [
        "memory_chunks",
        "agent_steps",
        "agent_runs",
        "user_agents",
        "backtest_results",
        "backtest_tasks",
        "trading_strategies",
        "chat_messages",
        "conversations",
        "support_resistance",
        "user_memory_files",
        "user_watchlist",
        "users",
        "index_valuations",
        "etf_premiums",
        "stock_fundamentals",
        "snapshot_realtime",
        "kline_1mon",
        "kline_1w",
        "kline_1d",
        "kline_15m",
        "symbols",
    ]
    drops = "\n".join(f'    op.execute("DROP TABLE IF EXISTS {t} CASCADE")' for t in tables)
    drops += '\n    op.execute("DROP FUNCTION IF EXISTS create_kline_partitions")\n    op.execute("DROP FUNCTION IF EXISTS set_updated_at")'
    content = f'''"""initial schema: 对齐 docs/sql/01_schema.sql + 03_agent_extensions.sql

Revision ID: 0001
Revises:
Create Date: 2026-08-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 与 docs/sql 保持一致的 DDL（BEGIN/COMMIT 已去除，交由 Alembic 事务管理）
SCHEMA_DDL = """
{ddl}
"""


def upgrade() -> None:
    op.execute(SCHEMA_DDL)


def downgrade() -> None:
    # 按依赖逆序删表（分区子表随父表 CASCADE 自动删除），并清理函数
{drops}
'''
    OUT.write_text(content, encoding="utf-8")
    print(f"generated: {OUT}")


if __name__ == "__main__":
    main()

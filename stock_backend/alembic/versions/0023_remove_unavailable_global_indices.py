"""Remove six unavailable global home indices.

Revision ID: 0023
Revises: 0022
"""

from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

INDICES = (
    ("N225", "日经指数", "JP", "513520", 9),
    ("KS11", "韩国综合", "KR", "", 10),
    ("DJI", "道琼斯指数", "US", "", 11),
    ("IXIC", "纳斯达克指数", "US", "513100", 12),
    ("INX", "标普500", "US", "513500", 13),
    ("XAU", "现货黄金", "XAU", "518880", 14),
)


def upgrade() -> None:
    connection = op.get_bind()
    # Block concurrent association writes until deletion and reordering commit.
    connection.execute(sa.text("LOCK TABLE symbols IN SHARE ROW EXCLUSIVE MODE"))
    ids = list(connection.scalars(sa.text(
        "SELECT id FROM symbols WHERE type = 'index' AND code IN :codes FOR UPDATE"
    ).bindparams(sa.bindparam("codes", expanding=True)), {"codes": [row[0] for row in INDICES]}))
    if ids:
        for table in ("user_watchlist", "support_resistance", "backtest_tasks",
                      "backtest_results", "chat_messages", "agent_runs"):
            count = connection.scalar(sa.text(
                f"SELECT count(*) FROM {table} WHERE symbol_id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True)), {"ids": ids})
            if count:
                raise RuntimeError(f"Cannot remove global indices: {table} has {count} user associations")
        connection.execute(sa.text(
            "DELETE FROM symbols WHERE id IN :ids"
        ).bindparams(sa.bindparam("ids", expanding=True)), {"ids": ids})
    connection.execute(sa.text(
        "UPDATE symbols SET sort_order = sort_order - 6 "
        "WHERE is_fixed_index = TRUE AND sort_order >= 15"
    ))


def downgrade() -> None:
    # Restore the seed list. Deleted market data requires a backup or resync.
    connection = op.get_bind()
    connection.execute(sa.text(
        "UPDATE symbols SET sort_order = sort_order + 6 "
        "WHERE is_fixed_index = TRUE AND sort_order >= 9"
    ))
    for code, name, market, etf, order in INDICES:
        connection.execute(sa.text(
            "INSERT INTO symbols (code, name, type, market, etf_linked, is_fixed_index, sort_order) "
            "VALUES (:code, :name, 'index', :market, :etf, TRUE, :order) "
            "ON CONFLICT (type, name) DO UPDATE SET is_fixed_index = TRUE, sort_order = EXCLUDED.sort_order"
        ), {"code": code, "name": name, "market": market, "etf": etf, "order": order})

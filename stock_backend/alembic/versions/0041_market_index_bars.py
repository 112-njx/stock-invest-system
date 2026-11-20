"""Store market page headline indices separately from StockDB history."""

from alembic import op
import sqlalchemy as sa

revision = "0041"
down_revision = "0040"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "market_index_bars",
        sa.Column("symbol_id", sa.Integer, sa.ForeignKey("symbols.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("period", sa.String(4), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), primary_key=True),
        *(sa.Column(field, sa.Numeric(30, 6), nullable=False) for field in ("open", "high", "low", "close")),
        sa.Column("pre_close", sa.Numeric(30, 6)),
        sa.Column("volume", sa.BigInteger, nullable=False),
        sa.Column("amount", sa.Numeric(24, 2), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.CheckConstraint("period IN ('1d', '15m', '1w', '1mon')", name="ck_market_index_bar_period"),
        sa.CheckConstraint("source IN ('qmt', 'eastmoney', 'sina')", name="ck_market_index_bar_source"),
    )
    op.create_index("ix_market_index_bars_updated_at", "market_index_bars", ["updated_at"])
    _replace_headline("932000", "000905", "中证500", "510500")


def downgrade():
    _replace_headline("000905", "932000", "中证2000", "563300")
    op.drop_table("market_index_bars")


def _replace_headline(old_code, code, name, etf):
    op.execute(sa.text(
        "UPDATE symbols SET is_fixed_index = FALSE, sort_order = NULL "
        "WHERE type = 'index' AND market = 'CSI' AND code = :code AND is_fixed_index"
    ).bindparams(code=old_code))
    op.execute(sa.text(
        "INSERT INTO symbols (code, name, type, market, etf_linked, is_fixed_index, sort_order) "
        "VALUES (:code, :name, 'index', 'CSI', :etf, TRUE, 8) "
        "ON CONFLICT (type, name) DO UPDATE SET code = EXCLUDED.code, market = EXCLUDED.market, "
        "etf_linked = EXCLUDED.etf_linked, is_fixed_index = TRUE, sort_order = 8"
    ).bindparams(code=code, name=name, etf=etf))

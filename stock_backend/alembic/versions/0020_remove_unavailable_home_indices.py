"""Remove unavailable sectors from the fixed home index list.

Revision ID: 0020
Revises: 0019
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

REMOVED_NAMES = ("创新药", "商业航天", "军工", "消费", "细分化工", "农业种植", "猪肉")


def upgrade() -> None:
    names = ", ".join(f"'{name}'" for name in REMOVED_NAMES)
    op.execute(
        f"UPDATE symbols SET is_fixed_index = FALSE, sort_order = NULL "
        f"WHERE type = 'index' AND name IN ({names})"
    )
    op.execute(
        "WITH ordered AS ("
        " SELECT id, ROW_NUMBER() OVER (ORDER BY sort_order NULLS LAST, id) AS new_order"
        " FROM symbols WHERE is_fixed_index = TRUE"
        ") UPDATE symbols AS s SET sort_order = ordered.new_order FROM ordered WHERE s.id = ordered.id"
    )


def downgrade() -> None:
    # Restore the compacted 42-row order to the original 49-row sort positions.
    restored_order = {
        24: 26, 25: 27, 26: 29, 27: 30, 28: 31, 29: 32, 30: 33,
        31: 36, 32: 37, 33: 38, 34: 39, 35: 41, 36: 42, 37: 44,
        38: 45, 39: 46, 40: 47, 41: 48, 42: 49,
    }
    cases = " ".join(f"WHEN {new} THEN {old}" for new, old in restored_order.items())
    op.execute(f"UPDATE symbols SET sort_order = CASE sort_order {cases} ELSE sort_order END WHERE is_fixed_index = TRUE")
    original_orders = {
        "创新药": 24,
        "商业航天": 25,
        "军工": 28,
        "消费": 34,
        "细分化工": 35,
        "农业种植": 40,
        "猪肉": 43,
    }
    for name, order in original_orders.items():
        op.execute(
            "UPDATE symbols SET is_fixed_index = TRUE, sort_order = "
            f"{order} WHERE type = 'index' AND name = '{name}'"
        )

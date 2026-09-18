"""V0.3 G14（P0-2）：users 加用户自填 API Key（密文）+ 累计 token 用量列。

- api_key_encrypted text 可空：用户自填 DeepSeek Key，AES-256-GCM 密文（明文禁止落库）；
  为空表示未填，AI 调用回退服务端默认 key。列类型 Text，加密由 ORM TypeDecorator 透明处理。
- llm_tokens_prompt / llm_tokens_completion bigint 非空默认 0：累计 token 用量（估算值，
  非精确计费），供个人设置页展示成本自估。
- 三列均可空/有默认值，存量行无需回填，向后兼容。

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("api_key_encrypted", sa.Text(), nullable=True))
    op.add_column(
        "users",
        sa.Column("llm_tokens_prompt", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "users",
        sa.Column("llm_tokens_completion", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("users", "llm_tokens_completion")
    op.drop_column("users", "llm_tokens_prompt")
    op.drop_column("users", "api_key_encrypted")

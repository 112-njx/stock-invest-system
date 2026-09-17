"""V0.3 G04（P1-12a）：pgvector 扩展 + memory_chunks 加 embedding/embedding_kind 列 + HNSW 索引。

- 启用 vector 扩展（pgvector 须预装在 PG 实例中，Docker 使用 pgvector/pgvector:pg16 镜像）。
- embedding vector(384)：对齐 EMBEDDING_DIM=384，nullable（迁移期存量行为空，G31 回填）。
- embedding_kind varchar(16)：区分 hash/minilm（等价原 ChromaDB collection 名后缀隔离）。
- HNSW 索引：余弦距离排序，加速 TopK 检索。
- 复合索引：(user_id, embedding_kind) 配合行级过滤。

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. 启用 pgvector 扩展（幂等）
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. memory_chunks 加 embedding vector(384) 列（nullable，G31 回填前为空）
    op.add_column(
        "memory_chunks",
        sa.Column("embedding", sa.Text(), nullable=True),  # 先以 text 添加，下方转 vector
    )
    op.execute(
        "ALTER TABLE memory_chunks "
        "ALTER COLUMN embedding TYPE vector(384) "
        "USING embedding::vector(384)"
    )

    # 3. memory_chunks 加 embedding_kind varchar(16) 列（nullable，hash/minilm）
    op.add_column(
        "memory_chunks",
        sa.Column("embedding_kind", sa.String(length=16), nullable=True),
    )

    # 4. HNSW 索引（余弦距离）—— 仅在 embedding 非空行上建索引
    op.execute(
        "CREATE INDEX ix_memory_chunks_embedding_hnsw "
        "ON memory_chunks USING hnsw (embedding vector_cosine_ops)"
    )

    # 5. 复合索引（user_id + embedding_kind）—— 配合行级过滤
    op.create_index(
        "ix_memory_chunks_user_embedding_kind",
        "memory_chunks",
        ["user_id", "embedding_kind"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_chunks_user_embedding_kind", table_name="memory_chunks")
    op.execute("DROP INDEX IF EXISTS ix_memory_chunks_embedding_hnsw")
    op.drop_column("memory_chunks", "embedding_kind")
    op.drop_column("memory_chunks", "embedding")
    # 注意：不 DROP EXTENSION vector，因为其它表/功能可能依赖

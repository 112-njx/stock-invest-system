"""G04（P1-12a）pgvector 迁移测试：扩展可用、memory_chunks 新列/索引、模型元数据。

测试分两层：
- 模型元数据测试：不依赖 DB，验证 MemoryChunk 模型含 embedding/embedding_kind 列。
- 集成测试：需本地 PG 运行且已安装 pgvector 扩展（Docker 环境自动满足）。
"""

import uuid

import pytest
from sqlalchemy import text

from app.models.agent import EMBEDDING_DIM, MemoryChunk
from app.utils.db import get_session


# ---- 模型元数据（无需 DB 连接）----
def test_memory_chunk_has_embedding_column():
    """MemoryChunk 模型含 embedding 列（Vector 类型，384 维）。"""
    cols = {c.name for c in MemoryChunk.__table__.columns}
    assert "embedding" in cols, f"embedding 列缺失，现有列：{cols}"


def test_memory_chunk_has_embedding_kind_column():
    """MemoryChunk 模型含 embedding_kind 列（varchar(16)）。"""
    cols = {c.name for c in MemoryChunk.__table__.columns}
    assert "embedding_kind" in cols, f"embedding_kind 列缺失，现有列：{cols}"


def test_embedding_dim_constant():
    """向量维度常量对齐 config.EMBEDDING_DIM=384。"""
    assert EMBEDDING_DIM == 384


def test_embedding_column_nullable():
    """embedding 列为 nullable（迁移期存量行为空，G31 回填后填充）。"""
    col = MemoryChunk.__table__.columns["embedding"]
    assert col.nullable is True, "embedding 列应为 nullable（迁移期兼容）"


def test_embedding_kind_column_nullable():
    """embedding_kind 列为 nullable（迁移期存量行为空）。"""
    col = MemoryChunk.__table__.columns["embedding_kind"]
    assert col.nullable is True, "embedding_kind 列应为 nullable（迁移期兼容）"


# ---- 迁移集成测试（需本地 PG + pgvector）----
def _pgvector_available() -> bool:
    """检测本地 PG 是否已安装 pgvector 扩展。"""
    try:
        db = get_session()
        try:
            result = db.execute(text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'"))
            return result.scalar() is not None
        finally:
            db.close()
    except Exception:
        return False


_skip_no_pg = pytest.mark.skipif(
    not _pgvector_available(),
    reason="本地 PG 未运行或未安装 pgvector 扩展（Docker 环境自动满足）",
)


@_skip_no_pg
def test_migration_creates_vector_extension():
    """迁移后 vector 扩展已创建。"""
    db = get_session()
    try:
        result = db.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
        assert result.scalar() == "vector", "vector 扩展未创建"
    finally:
        db.close()


@_skip_no_pg
def test_migration_adds_embedding_column():
    """迁移后 memory_chunks.embedding 列存在且类型为 vector(384)。"""
    db = get_session()
    try:
        result = db.execute(
            text(
                "SELECT data_type, udt_name FROM information_schema.columns "
                "WHERE table_name = 'memory_chunks' AND column_name = 'embedding'"
            )
        )
        row = result.fetchone()
        assert row is not None, "embedding 列不存在"
        assert row[1] == "vector", f"embedding 列类型错误：{row}"
    finally:
        db.close()


@_skip_no_pg
def test_migration_adds_embedding_kind_column():
    """迁移后 memory_chunks.embedding_kind 列存在。"""
    db = get_session()
    try:
        result = db.execute(
            text(
                "SELECT data_type, character_maximum_length FROM information_schema.columns "
                "WHERE table_name = 'memory_chunks' AND column_name = 'embedding_kind'"
            )
        )
        row = result.fetchone()
        assert row is not None, "embedding_kind 列不存在"
        assert row[0] == "character varying", f"embedding_kind 列类型错误：{row}"
        assert row[1] == 16, f"embedding_kind 长度应为 16：{row}"
    finally:
        db.close()


@_skip_no_pg
def test_hnsw_index_exists():
    """迁移后 HNSW 索引已创建。"""
    db = get_session()
    try:
        result = db.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'memory_chunks' AND indexname = 'ix_memory_chunks_embedding_hnsw'"
            )
        )
        assert result.scalar() is not None, "HNSW 索引 ix_memory_chunks_embedding_hnsw 不存在"
    finally:
        db.close()


@_skip_no_pg
def test_composite_index_exists():
    """迁移后 (user_id, embedding_kind) 复合索引已创建。"""
    db = get_session()
    try:
        result = db.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'memory_chunks' AND indexname = 'ix_memory_chunks_user_embedding_kind'"
            )
        )
        assert result.scalar() is not None, "复合索引 ix_memory_chunks_user_embedding_kind 不存在"
    finally:
        db.close()


@_skip_no_pg
def test_vector_insert_and_cosine_distance():
    """验证 vector 列可写入 384 维向量，余弦距离计算正确。"""
    import numpy as np

    db = get_session()
    uname = f"pgv_{uuid.uuid4().hex[:8]}"
    try:
        # 建临时用户（memory_chunks.user_id 有外键约束）
        uid = db.execute(
            text(
                "INSERT INTO users (username, password_hash) VALUES (:u, 'x') RETURNING id"
            ),
            {"u": uname},
        ).scalar()
        db.commit()

        # 生成归一化测试向量
        vec = np.random.randn(EMBEDDING_DIM).astype(np.float32)
        vec = vec / np.linalg.norm(vec)
        vec_str = "[" + ",".join(str(float(v)) for v in vec) + "]"

        # 插入测试行（CAST 而非 :: 转型，避免 SQLAlchemy 误解析绑定参数）
        db.execute(
            text(
                "INSERT INTO memory_chunks (user_id, source_type, content, importance, embedding, embedding_kind) "
                "VALUES (:uid, 'test', 'pgvector_test', 5, CAST(:vec AS vector), 'hash')"
            ),
            {"uid": uid, "vec": vec_str},
        )
        db.commit()

        # 余弦距离查询（自身距离应为 0）
        result = db.execute(
            text(
                "SELECT embedding <=> CAST(:vec AS vector) AS distance "
                "FROM memory_chunks WHERE user_id = :uid AND content = 'pgvector_test' LIMIT 1"
            ),
            {"uid": uid, "vec": vec_str},
        )
        distance = result.scalar()
        assert distance is not None, "余弦距离查询失败"
        assert abs(float(distance)) < 1e-5, f"自身余弦距离应为 ~0，实际为 {distance}"

        # 正交向量距离应接近 1（余弦距离 = 1 - 余弦相似度）
        orth = np.zeros(EMBEDDING_DIM, dtype=np.float32)
        orth[0] = 1.0
        orth_str = "[" + ",".join(str(float(v)) for v in orth) + "]"
        result = db.execute(
            text(
                "SELECT embedding <=> CAST(:vec AS vector) AS distance "
                "FROM memory_chunks WHERE user_id = :uid AND content = 'pgvector_test' LIMIT 1"
            ),
            {"uid": uid, "vec": orth_str},
        )
        dist2 = float(result.scalar())
        assert 0.0 <= dist2 <= 2.0, f"余弦距离应在 [0,2] 区间，实际 {dist2}"
    finally:
        # 清理（先删 chunk 再删 user，避免外键阻塞）
        db.execute(text("DELETE FROM memory_chunks WHERE user_id = (SELECT id FROM users WHERE username = :u)"), {"u": uname})
        db.execute(text("DELETE FROM users WHERE username = :u"), {"u": uname})
        db.commit()
        db.close()

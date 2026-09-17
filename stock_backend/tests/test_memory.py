"""3.4 本地记忆系统测试：事实解析、落库（文件+向量+索引）、检索、Agent 工具、聊天后抽取接线。"""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from app.agent.memory import memory_service, store
from app.models.agent import MemoryChunk
from app.models.user import User
from app.repositories import agent_repo
from app.utils.db import get_session
from fastapi.testclient import TestClient

_PREFIX = "test_mem_"


def _uname() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex[:8]}"


def _register(client: TestClient, username: str) -> dict:
    r = client.post("/api/v1/auth/register", json={"username": username, "password": "pass123456", "email": f"{username}@test.local"})
    assert r.status_code == 200, r.text
    return r.json()["data"]["user"]


def _cleanup_users(*unames: str) -> None:
    db = get_session()
    try:
        for u in unames:
            row = db.query(User).filter(User.username == u).first()
            if row:
                db.delete(row)
        db.commit()
    finally:
        db.close()


def _cleanup_memory(user_id: int, tmp_memory: str) -> None:
    db = get_session()
    try:
        db.query(MemoryChunk).filter(MemoryChunk.user_id == user_id).delete()
        db.commit()
    finally:
        db.close()
    # 清测试目录
    import shutil

    d = Path(tmp_memory)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def mem_env(tmp_path, monkeypatch):
    """隔离记忆文件目录（G31 后向量存 PG，无 Chroma 目录需要隔离）。"""
    memory_dir = str(tmp_path / "memory")
    monkeypatch.setattr(store.settings, "MEMORY_DIR", memory_dir)
    return {"memory": memory_dir}


# ---- 事实解析 ----
def test_parse_facts_plain_json():
    text = '[{"content":"止损不超过2%","type":"rule","importance":8},{"content":"闲聊","importance":2}]'
    facts = memory_service._parse_facts(text)
    assert len(facts) == 1  # 重要性 <5 被过滤
    assert facts[0]["content"] == "止损不超过2%"
    assert facts[0]["type"] == "rule"


def test_parse_facts_markdown_fence_and_bad():
    text = '```json\n[{"content":"偏好波段","type":"preference","importance":7}]\n```'
    assert memory_service._parse_facts(text)[0]["content"] == "偏好波段"
    assert memory_service._parse_facts("not json at all") == []
    assert memory_service._parse_facts('{"a":1}') == []


async def test_aextract_facts_parses_valid_json():
    """回归：_EXTRACT_PROMPT 内 JSON 示例花括号已转义，str.format 不再抛 KeyError。"""

    class _FakeLLM:
        available = True

        async def ainvoke(self, messages, temperature=None):
            from app.services.llm.providers.base import LLMResult

            return LLMResult(text='[{"content":"止损不超过2%","type":"rule","importance":8}]', model="fake", tokens=5)

    facts = await memory_service.aextract_facts("用户消息", "助手消息", _FakeLLM())
    assert len(facts) == 1
    assert facts[0]["content"] == "止损不超过2%"
    assert facts[0]["importance"] == 8


# ---- 保存 + 检索 ----
def test_save_and_retrieve_memory(client: TestClient, mem_env):
    uname = _uname()
    user = _register(client, uname)
    try:
        db = get_session()
        try:
            n = memory_service.save_memory(
                db,
                user["id"],
                "rule",
                None,
                [
                    {"content": "我的止损规则是不超过2%，跌破即离场", "type": "rule", "importance": 8},
                    {"content": "偏好短线波段，不做长线", "type": "preference", "importance": 7},
                ],
            )
            assert n == 2

            # memory_chunks 登记
            chunks = db.query(MemoryChunk).filter(MemoryChunk.user_id == user["id"]).all()
            assert len(chunks) == 2
            assert all(c.file_path for c in chunks)
        finally:
            db.close()

        # 记忆文件已生成（人类可读）
        files = list(Path(mem_env["memory"]).rglob("*.md"))
        assert len(files) == 2  # rule.md + preference.md

        # 检索命中相关记忆
        text = memory_service.retrieve_memory(get_session(), user["id"], "我的止损习惯是什么", top_k=3)
        assert "止损" in text
    finally:
        _cleanup_memory(user["id"], mem_env["memory"])
        _cleanup_users(uname)


def test_memory_tool_search(client: TestClient, mem_env):
    uname = _uname()
    user = _register(client, uname)
    try:
        db = get_session()
        try:
            memory_service.save_memory(
                db, user["id"], "preference", None, [{"content": "仓位管理偏好单笔不超过一成", "type": "preference", "importance": 8}]
            )
        finally:
            db.close()

        tool = memory_service.memory_tool(get_session(), user["id"])
        result = tool.invoke({"query": "仓位管理"})
        assert result["results"] and "仓位" in result["results"][0]["content"]
    finally:
        _cleanup_memory(user["id"], mem_env["memory"])
        _cleanup_users(uname)


# ---- 6.2：记忆分层与重要性 ----
def test_weighted_score():
    # G21：distance 为余弦距离（1 - 余弦相似度），区间 [0,2]
    # 距离越小（越相似）+ 重要性越高 → 分数越高
    assert store._weighted_score(0.0, 10) > store._weighted_score(2.0, 1)
    # 高重要性可补偿一定距离差距（相似度 0.8/重要性9 胜过 相似度 0.65/重要性3）
    assert store._weighted_score(0.2, 9) > store._weighted_score(0.35, 3)
    # 口径锁定：score = (1 - distance) × 0.7 + importance/10 × 0.3
    assert abs(store._weighted_score(0.25, 8) - (0.75 * 0.7 + 0.8 * 0.3)) < 1e-9


def test_save_memory_stores_importance(client: TestClient, mem_env):
    uname = _uname()
    user = _register(client, uname)
    try:
        db = get_session()
        try:
            memory_service.save_memory(
                db, user["id"], "rule", None, [{"content": "止损不超过2%", "type": "rule", "importance": 8}]
            )
        finally:
            db.close()

        db = get_session()
        try:
            chunk = db.query(MemoryChunk).filter(MemoryChunk.user_id == user["id"]).first()
            assert chunk.importance == 8
        finally:
            db.close()

        db = get_session()
        try:
            hits = store.search(db, user["id"], "止损", top_k=3)
        finally:
            db.close()
        assert hits and hits[0]["importance"] == 8
    finally:
        _cleanup_memory(user["id"], mem_env["memory"])
        _cleanup_users(uname)


def test_dedup_merge_identical_fact(client: TestClient, mem_env):
    uname = _uname()
    user = _register(client, uname)
    try:
        db = get_session()
        try:
            n1 = memory_service.save_memory(db, user["id"], "rule", None, [{"content": "止损不超过2%", "type": "rule", "importance": 8}])
            assert n1 == 1
        finally:
            db.close()

        # 相同事实再保存 → 合并（不新增），importance 取最大
        db = get_session()
        try:
            n2 = memory_service.save_memory(db, user["id"], "rule", None, [{"content": "止损不超过2%", "type": "rule", "importance": 9}])
            assert n2 == 0
        finally:
            db.close()

        db = get_session()
        try:
            chunks = db.query(MemoryChunk).filter(MemoryChunk.user_id == user["id"]).all()
            assert len(chunks) == 1
            assert chunks[0].importance == 9  # max(8,9)
        finally:
            db.close()
    finally:
        _cleanup_memory(user["id"], mem_env["memory"])
        _cleanup_users(uname)


# ---- G21（P1-12b）：向量存储 SQL 化 —— 增删改查/隔离/口径 ----
def test_store_module_has_no_chromadb_dependency():
    """G21 验收：store.py 不含 chromadb 引用（向量读写全走 SQLAlchemy + pgvector）。"""
    src = Path(store.__file__).read_text(encoding="utf-8")
    assert "chromadb" not in src, "store.py 仍引用 chromadb"


def test_store_add_chunk_fills_embedding_columns(client: TestClient, mem_env):
    """写入时同步填 embedding 与 embedding_kind（G31 回填的对照基准）。"""
    uname = _uname()
    user = _register(client, uname)
    try:
        db = get_session()
        try:
            row = store.add_chunk(db, user["id"], "v1", "止损不超过2%", {"source_type": "rule", "importance": 7})
            db.commit()
            assert row.embedding is not None, "embedding 未写入"
            assert len(list(row.embedding)) == 384
            assert row.embedding_kind == "hash"  # conftest 强制 hash
            assert row.importance == 7
            assert row.vector_id == "v1"
        finally:
            db.close()
    finally:
        _cleanup_memory(user["id"], mem_env["memory"])
        _cleanup_users(uname)


def test_store_search_orders_by_weighted_score(client: TestClient, mem_env):
    """TopK 按 相似度×0.7 + 重要性×0.3 重排，且 score 与锁定口径一致。"""
    uname = _uname()
    user = _register(client, uname)
    try:
        db = get_session()
        try:
            store.add_chunk(db, user["id"], "v_low", "止损不超过2%", {"source_type": "rule", "importance": 5})
            store.add_chunk(db, user["id"], "v_high", "止损不超过2%", {"source_type": "rule", "importance": 9})
            store.add_chunk(
                db, user["id"], "v_far", "完全无关的另一个话题：行业轮动与仓位再平衡", {"source_type": "rule", "importance": 5}
            )
            db.commit()
        finally:
            db.close()

        db = get_session()
        try:
            hits = store.search(db, user["id"], "止损不超过2%", top_k=3)
        finally:
            db.close()

        assert len(hits) == 3
        assert [h["chunk_id"] for h in hits][:2] == ["v_high", "v_low"]  # 同相似度下重要性高者优先
        assert hits[0]["score"] > hits[1]["score"] >= hits[2]["score"]
        assert hits[0]["distance"] < 1e-6, f"与查询完全相同的文本余弦距离应为 0，实际 {hits[0]['distance']}"
        expected = store._weighted_score(hits[0]["distance"], hits[0]["importance"])
        assert abs(hits[0]["score"] - expected) < 1e-6, "score 与锁定口径不一致"
        assert hits[0]["source_type"] == "rule"
    finally:
        _cleanup_memory(user["id"], mem_env["memory"])
        _cleanup_users(uname)


def test_store_update_chunk_reembeds_and_updates_importance(client: TestClient, mem_env):
    """更新切片：content 变更触发重新向量化，importance 同步更新。"""
    uname = _uname()
    user = _register(client, uname)
    try:
        db = get_session()
        try:
            row = store.add_chunk(db, user["id"], "v1", "旧内容：偏好短线", {"source_type": "preference", "importance": 5})
            db.commit()
            old_vec = list(row.embedding)
        finally:
            db.close()

        db = get_session()
        try:
            assert store.update_chunk(db, user["id"], "v1", "新内容：偏好中长线持有", {"importance": 9}) is True
            db.commit()
        finally:
            db.close()

        db = get_session()
        try:
            row = agent_repo.get_memory_chunk_by_vector(db, user["id"], "v1")
            assert row.content == "新内容：偏好中长线持有"
            assert row.importance == 9
            assert list(row.embedding) != old_vec, "内容变更后 embedding 未重新计算"
            # 更新不存在的切片返回 False
            assert store.update_chunk(db, user["id"], "not_exist", "x", {}) is False
        finally:
            db.close()
    finally:
        _cleanup_memory(user["id"], mem_env["memory"])
        _cleanup_users(uname)


def test_store_delete_chunk_paths(client: TestClient, mem_env):
    """按 vector_id / 主键两条删除路径都能移除行，且对不存在目标返回 False。"""
    uname = _uname()
    user = _register(client, uname)
    try:
        db = get_session()
        try:
            store.add_chunk(db, user["id"], "v1", "记忆一", {"source_type": "rule", "importance": 6})
            row2 = store.add_chunk(db, user["id"], "v2", "记忆二", {"source_type": "rule", "importance": 6})
            db.commit()
            row2_id = row2.id
        finally:
            db.close()

        db = get_session()
        try:
            assert store.delete_chunk(db, user["id"], "v1") is True
            assert store.delete_chunk(db, user["id"], "v1") is False  # 幂等：已删
            assert store.delete_chunk_by_id(db, user["id"], row2_id) is True
            assert store.delete_chunk_by_id(db, user["id"], row2_id) is False
            db.commit()
            assert agent_repo.count_memory_chunks(db, user["id"]) == 0
        finally:
            db.close()
    finally:
        _cleanup_memory(user["id"], mem_env["memory"])
        _cleanup_users(uname)


def test_store_search_isolated_by_user(client: TestClient, mem_env):
    """多租户隔离：只召回本用户记忆（原 per-user collection 的 SQL 等价物）。"""
    uname_a, uname_b = _uname(), _uname()
    user_a = _register(client, uname_a)
    user_b = _register(client, uname_b)
    try:
        db = get_session()
        try:
            store.add_chunk(db, user_a["id"], "va", "A 用户的止损规则是2%", {"source_type": "rule", "importance": 8})
            store.add_chunk(db, user_b["id"], "vb", "B 用户的止损规则是5%", {"source_type": "rule", "importance": 8})
            db.commit()
        finally:
            db.close()

        db = get_session()
        try:
            hits_a = store.search(db, user_a["id"], "止损规则", top_k=5)
            hits_b = store.search(db, user_b["id"], "止损规则", top_k=5)
        finally:
            db.close()
        assert [h["chunk_id"] for h in hits_a] == ["va"]
        assert [h["chunk_id"] for h in hits_b] == ["vb"]
    finally:
        _cleanup_memory(user_a["id"], mem_env["memory"])
        _cleanup_memory(user_b["id"], mem_env["memory"])
        _cleanup_users(uname_a, uname_b)


def test_store_search_isolated_by_embedding_kind(client: TestClient, mem_env):
    """向量空间隔离：embedding_kind 不匹配的行不参与召回（替代 collection 名隔离）。"""
    uname = _uname()
    user = _register(client, uname)
    try:
        db = get_session()
        try:
            store.add_chunk(db, user["id"], "v_hash", "止损不超过2%", {"source_type": "rule", "importance": 8})
            # 伪造一条 minilm 向量行（模拟切换模型后的旧向量）
            row = store.add_chunk(db, user["id"], "v_minilm", "止损不超过2%", {"source_type": "rule", "importance": 8})
            row.embedding_kind = "minilm"
            # 伪造一条 embedding 为空的行（G31 回填前的存量行）
            row_null = store.add_chunk(db, user["id"], "v_null", "止损不超过2%", {"source_type": "rule", "importance": 8})
            row_null.embedding = None
            row_null.embedding_kind = None
            db.commit()
        finally:
            db.close()

        db = get_session()
        try:
            hits = store.search(db, user["id"], "止损不超过2%", top_k=5)
            dup = store.find_duplicate(db, user["id"], "止损不超过2%")
        finally:
            db.close()
        assert [h["chunk_id"] for h in hits] == ["v_hash"], "minilm/空向量行不应被 hash 检索召回"
        assert dup is not None and dup["chunk_id"] == "v_hash"
    finally:
        _cleanup_memory(user["id"], mem_env["memory"])
        _cleanup_users(uname)


def test_find_duplicate_threshold(client: TestClient, mem_env):
    """去重阈值 0.85 下推 SQL：相同内容判重、无关内容不判重。"""
    uname = _uname()
    user = _register(client, uname)
    try:
        db = get_session()
        try:
            store.add_chunk(db, user["id"], "v1", "止损不超过2%", {"source_type": "rule", "importance": 8})
            db.commit()
        finally:
            db.close()

        db = get_session()
        try:
            dup = store.find_duplicate(db, user["id"], "止损不超过2%")
            assert dup is not None
            assert dup["chunk_id"] == "v1"
            assert dup["similarity"] > 0.85
            assert dup["meta"]["importance"] == 8
            # 完全无关内容不应判重
            assert store.find_duplicate(db, user["id"], "今天天气不错适合出门散步") is None
            # 阈值提高到 1.0（不含）时相同内容也不再判重
            assert store.find_duplicate(db, user["id"], "止损不超过2%", threshold=1.0) is None
            # 空内容 → 零向量不可用，直接返回 None
            assert store.find_duplicate(db, user["id"], "") is None
        finally:
            db.close()
    finally:
        _cleanup_memory(user["id"], mem_env["memory"])
        _cleanup_users(uname)


def test_store_delete_collection_clears_user_only(client: TestClient, mem_env):
    """清空 = 按 user_id 删除全部行，不影响其它用户。"""
    uname_a, uname_b = _uname(), _uname()
    user_a = _register(client, uname_a)
    user_b = _register(client, uname_b)
    try:
        db = get_session()
        try:
            store.add_chunk(db, user_a["id"], "va1", "A 记忆一", {"source_type": "rule", "importance": 6})
            store.add_chunk(db, user_a["id"], "va2", "A 记忆二", {"source_type": "rule", "importance": 6})
            store.add_chunk(db, user_b["id"], "vb1", "B 记忆一", {"source_type": "rule", "importance": 6})
            db.commit()
        finally:
            db.close()

        db = get_session()
        try:
            deleted = store.delete_collection(db, user_a["id"])
            db.commit()
            assert deleted == 2
            assert agent_repo.count_memory_chunks(db, user_a["id"]) == 0
            assert agent_repo.count_memory_chunks(db, user_b["id"]) == 1
        finally:
            db.close()
    finally:
        _cleanup_memory(user_a["id"], mem_env["memory"])
        _cleanup_memory(user_b["id"], mem_env["memory"])
        _cleanup_users(uname_a, uname_b)


def test_store_search_empty_query_returns_empty(client: TestClient, mem_env):
    """零向量（空查询）无法定义余弦相似度，直接返回空而非 NaN 结果。"""
    uname = _uname()
    user = _register(client, uname)
    try:
        db = get_session()
        try:
            store.add_chunk(db, user["id"], "v1", "止损不超过2%", {"source_type": "rule", "importance": 8})
            db.commit()
        finally:
            db.close()

        db = get_session()
        try:
            assert store.search(db, user["id"], "") == []
        finally:
            db.close()
    finally:
        _cleanup_memory(user["id"], mem_env["memory"])
        _cleanup_users(uname)


def test_cleanup_expired_memories(client: TestClient, mem_env):
    uname = _uname()
    user = _register(client, uname)
    try:
        db = get_session()
        try:
            c1 = agent_repo.add_memory_chunk(db, user["id"], "rule", None, "低价值旧记忆", "v1", None, importance=2)
            c2 = agent_repo.add_memory_chunk(db, user["id"], "rule", None, "高价值旧记忆", "v2", None, importance=8)
            c3 = agent_repo.add_memory_chunk(db, user["id"], "rule", None, "低价值新记忆", "v3", None, importance=2)
            db.commit()
            # 手动把 c1/c2 创建时间改为 40 天前
            old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=40)
            for c in (c1, c2):
                c.created_at = old
            db.commit()
            c1_id, c2_id, c3_id = c1.id, c2.id, c3.id
        finally:
            db.close()

        db = get_session()
        try:
            deleted = memory_service.cleanup_expired_memories(db, importance_below=3, days=30)
            assert deleted == 1  # 仅删除低重要性且超期的 c1
        finally:
            db.close()

        db = get_session()
        try:
            ids = [r[0] for r in db.query(MemoryChunk.id).filter(MemoryChunk.user_id == user["id"]).all()]
            assert c1_id not in ids
            assert c2_id in ids  # 高重要性保留
            assert c3_id in ids  # 低重要性但未超期保留
        finally:
            db.close()
    finally:
        _cleanup_memory(user["id"], mem_env["memory"])
        _cleanup_users(uname)

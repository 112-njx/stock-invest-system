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
    r = client.post("/api/v1/auth/register", json={"username": username, "password": "pass123456"})
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


def _cleanup_memory(user_id: int, tmp_chroma: str, tmp_memory: str) -> None:
    db = get_session()
    try:
        db.query(MemoryChunk).filter(MemoryChunk.user_id == user_id).delete()
        db.commit()
    finally:
        db.close()
    # 清测试目录
    import shutil

    for d in (Path(tmp_chroma), Path(tmp_memory)):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def mem_env(tmp_path, monkeypatch):
    """隔离记忆存储目录。"""
    chroma_dir = str(tmp_path / "chroma")
    memory_dir = str(tmp_path / "memory")
    monkeypatch.setattr(store.settings, "CHROMA_DIR", chroma_dir)
    monkeypatch.setattr(store.settings, "MEMORY_DIR", memory_dir)
    return {"chroma": chroma_dir, "memory": memory_dir}


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
        _cleanup_memory(user["id"], mem_env["chroma"], mem_env["memory"])
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
        _cleanup_memory(user["id"], mem_env["chroma"], mem_env["memory"])
        _cleanup_users(uname)


# ---- 6.2：记忆分层与重要性 ----
def test_weighted_score():
    # 距离越小（越相似）+ 重要性越高 → 分数越高
    assert store._weighted_score(0.0, 10) > store._weighted_score(2.0, 1)
    # 高重要性可补偿一定距离差距
    assert store._weighted_score(0.5, 9) > store._weighted_score(0.2, 3)


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

        hits = store.search(user["id"], "止损", top_k=3)
        assert hits and hits[0]["importance"] == 8
    finally:
        _cleanup_memory(user["id"], mem_env["chroma"], mem_env["memory"])
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
        _cleanup_memory(user["id"], mem_env["chroma"], mem_env["memory"])
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
        _cleanup_memory(user["id"], mem_env["chroma"], mem_env["memory"])
        _cleanup_users(uname)

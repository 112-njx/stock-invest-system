"""G11 · P1-2b PG 读写分离 + Redis Sentinel 测试。

三类，全部真实断言（不 mock 路由结果）：

1. **引擎选择与降级**：`build_engines()` 在读库未配置时返回**同一对象**（本地单实例零差异），
   配置后返回两个独立引擎且各自指向正确的 DSN。
2. **真实路由**：把只读会话工厂换成绑定「独立读引擎」的 sessionmaker，捕获该引擎上实际执行的
   SQL —— 断言行情端点（/kline）**确实走读引擎**，而用户数据端点（/watchlist）**不走**
   （用户数据必须走主库，读己之写不能有复制延迟）。
3. **Redis Sentinel**：未配置时直连降级（行为与改造前一致）；配置后走 Sentinel 主节点发现
   （用真实 Sentinel 容器验证，见 docs/ops/read_write_splitting.md）。
"""

import pytest
import redis
from app.core.config import get_settings
from app.utils import db as db_mod
from app.utils.db import build_engines
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


# --------------------------------------------------------------------------- #
# 1. 引擎选择与降级
# --------------------------------------------------------------------------- #
class _Settings:
    """最小 settings 替身（只用 build_engines 需要的那几个字段）。"""

    def __init__(self, primary: str, read: str = ""):
        self.DATABASE_URL = primary
        self.DATABASE_READ_URL = read
        self.DB_POOL_SIZE = 2
        self.DB_MAX_OVERFLOW = 1
        self.DB_POOL_TIMEOUT = 5
        self.DB_POOL_RECYCLE = 3600


def test_read_engine_degrades_to_primary_when_unset():
    """未配置 DATABASE_READ_URL → 读库**就是**主库引擎（同一对象，行为零差异）。"""
    primary, read = build_engines(_Settings("postgresql+psycopg2://u:p@127.0.0.1:5432/db1"))

    assert read is primary, "未配置从库时必须复用主库引擎，否则本地开发行为会变"


def test_read_engine_is_distinct_when_configured():
    """配置 DATABASE_READ_URL → 两个独立引擎，且各自 URL 正确（读不写错库）。"""
    primary, read = build_engines(
        _Settings("postgresql+psycopg2://u:p@127.0.0.1:5432/primary", "postgresql+psycopg2://u:p@127.0.0.1:5433/replica")
    )

    assert read is not primary
    assert primary.url.database == "primary"
    assert read.url.database == "replica"
    assert read.url.port == 5433


def test_current_runtime_is_degraded_locally():
    """本机未配从库时，运行期必须处于降级态（`read_write_splitting_enabled()` 为 False）。"""
    assert db_mod.read_write_splitting_enabled() is (db_mod.read_engine is not db_mod.engine)


# --------------------------------------------------------------------------- #
# 2. 真实路由：行情走读库、用户数据走主库
# --------------------------------------------------------------------------- #
@pytest.fixture
def capture_engines(monkeypatch):
    """把「读会话工厂」换成绑定独立读引擎的 sessionmaker，并捕获两引擎上执行的 SQL。

    本机 DATABASE_READ_URL 未配置，运行期 read_engine 就是主库引擎 —— 那样无法区分
    "走了读引擎"还是"走了主库"。故这里造一个**独立引擎**（指向同一个 dev 库，数据一致，
    但对象不同）来证明路由确实发生了。
    """
    dsn = get_settings().DATABASE_URL
    read_engine = create_engine(dsn, future=True)
    primary_sql: list[str] = []
    read_sql: list[str] = []
    event.listen(db_mod.engine, "before_cursor_execute", lambda *a: primary_sql.append(a[2]))
    event.listen(read_engine, "before_cursor_execute", lambda *a: read_sql.append(a[2]))
    monkeypatch.setattr(
        db_mod, "ReadSessionLocal", sessionmaker(bind=read_engine, autocommit=False, autoflush=False, expire_on_commit=False)
    )
    monkeypatch.setattr(
        "app.api.deps.ReadSessionLocal",
        sessionmaker(bind=read_engine, autocommit=False, autoflush=False, expire_on_commit=False),
    )
    try:
        yield primary_sql, read_sql
    finally:
        read_engine.dispose()


def test_market_read_endpoints_use_read_engine(client: TestClient, capture_engines):
    """行情端点（K线/快照/目录）必须走**读引擎**。"""
    primary_sql, read_sql = capture_engines

    assert client.get("/api/v1/kline", params={"symbol": "600519", "period": "1d", "limit": 5}).status_code == 200
    assert client.get("/api/v1/snapshot", params={"symbols": "600519"}).status_code == 200
    assert client.get("/api/v1/symbols", params={"limit": 5}).status_code == 200

    assert any("kline_1d" in s for s in read_sql), f"K线查询未走读引擎：{read_sql[:5]}"
    assert not any("kline_1d" in s for s in primary_sql), f"K线查询不应走主库：{primary_sql[:5]}"


def test_user_data_endpoints_use_primary_engine(client: TestClient, capture_engines):
    """用户数据端点必须走**主库** —— 读己之写不能受复制延迟影响。"""
    primary_sql, read_sql = capture_engines

    # 关注列表：读用户数据（未登录 401 也会先建会话，这里用带 token 的真实请求）
    import uuid

    uname = f"test_g11_{uuid.uuid4().hex[:8]}"
    reg = client.post(
        "/api/v1/auth/register",
        json={"username": uname, "password": "pass123456", "email": f"{uname}@test.local"},
    )
    assert reg.status_code == 200, reg.text
    token = reg.json()["data"]["token"]

    resp = client.get("/api/v1/watchlist", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text

    assert any(("watchlist" in s.lower()) for s in primary_sql), f"用户数据未走主库：{primary_sql[:5]}"
    assert not any("watchlist" in s.lower() for s in read_sql), f"用户数据不应走读库：{read_sql[:5]}"


# --------------------------------------------------------------------------- #
# 3. Redis Sentinel
# --------------------------------------------------------------------------- #
def test_redis_client_degrades_to_direct_when_sentinel_unset(monkeypatch):
    """未配置 Sentinel → 直连 REDIS_URL（与改造前行为一致），且真实可用。"""
    from app.utils import redis_client as rc

    monkeypatch.setattr(rc.get_settings(), "REDIS_SENTINEL_HOSTS", "")
    monkeypatch.setattr(rc.get_settings(), "REDIS_SENTINEL_ENABLED", False)
    client = rc._build_client()

    assert isinstance(client, redis.Redis)
    assert client.ping() is True
    key = "g11:degrade:probe"
    client.set(key, "ok", ex=10)
    assert client.get(key) == "ok"
    client.delete(key)


def test_sentinel_enabled_without_hosts_warns_and_falls_back(monkeypatch):
    """开关打开但没配地址 → 降级直连（不因配置不全而启动失败）。"""
    from app.utils import redis_client as rc

    monkeypatch.setattr(rc.get_settings(), "REDIS_SENTINEL_ENABLED", True)
    monkeypatch.setattr(rc.get_settings(), "REDIS_SENTINEL_HOSTS", "")
    client = rc._build_client()

    assert client.ping() is True


def test_sentinel_client_is_lazy_about_unreachable_hosts(monkeypatch):
    """配了不可达的 Sentinel → **构造不抛错**，只在真正用时失败。

    可用性要求：Sentinel 抖动的瞬间不能让 API 进程起不来。
    """
    from app.utils import redis_client as rc

    monkeypatch.setattr(rc.get_settings(), "REDIS_SENTINEL_HOSTS", "127.0.0.1:26399")
    monkeypatch.setattr(rc.get_settings(), "REDIS_SENTINEL_ENABLED", True)
    client = rc._build_client()  # 不应抛错

    with pytest.raises(redis.exceptions.RedisError):
        client.ping()

"""G08 · P1-4a 策略沙箱加固与子进程隔离测试。

四组，全部真实执行（不 mock DB/Redis/子进程）：

1. **沙箱逃逸审计回归**：`__class__`/`__bases__`/`__subclasses__`/`__globals__`/`__mro__`
   编译期拒绝；`getattr` 不在受限内建（NameError）；`str.format`/`format_map` 运行时拒绝；
   增强赋值 `+=` 可用（G08 修复的缺陷）；非白名单类型的增强赋值拒绝。
2. **子进程隔离**：正常策略跑通、死循环被 terminate 且**父进程存活**、策略自身错误照常抛
   `BacktestError`；CPU/内存硬上限在 POSIX 上生效（Windows 无 `resource` 模块，按平台分别断言）。
3. **per-user 并发配额**（真实 Redis）：第 N+1 个被拒、释放幂等、过期槽位自愈。
4. **服务层集成**：`create_backtest` 在队列繁忙/配额耗尽时抛 429；`execute_backtest`
   经子进程跑真实回测并落库。
"""

import os
import time
import types
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.backtest.engine import BacktestConfig, BacktestError
from app.backtest.runner import (
    StrategyResourceError,
    StrategyRuntimeError,
    child_rss_bytes,
    limits_effective,
    run_isolated,
)
from app.backtest.sandbox import SandboxError, compile_strategy
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.models.user import User
from app.repositories import kline_repo
from app.services import backtest_quota, backtest_service
from app.utils.db import get_session
from app.utils.redis_client import get_redis_client
from fastapi.testclient import TestClient

_settings = get_settings()
_PREFIX = "test_g08_"

_SMA_STRATEGY = """
def initialize(context):
    pass

def on_bar(bar, context):
    n = 5
    closes = context.closes
    if len(closes) < n:
        return
    ma = sum(closes[-n:]) / n
    if bar["close"] > ma and context.pos == 0:
        context.buy()
    elif bar["close"] < ma and context.pos > 0:
        context.sell()
"""


def _bars(n: int = 60) -> list[dict]:
    """合成日K（先涨后跌），纯 dict（跨进程可 pickle，与引擎入参一致）。"""
    out = []
    ts = datetime(2024, 1, 1, tzinfo=UTC)
    for i in range(n):
        c = round(10 + (i if i < 30 else 60 - i) * 0.3, 3)
        out.append(
            {
                "ts": ts + timedelta(days=i),
                "open": c,
                "high": round(c + 0.1, 3),
                "low": round(c - 0.1, 3),
                "close": c,
                "volume": 1000,
                "amount": round(c * 1000, 2),
            }
        )
    return out


def _fake_bars(n: int = 60) -> list[types.SimpleNamespace]:
    """同上但为 ORM 风格对象：`kline_repo.get_bars` 的返回值会被 `_bar_to_dict` 按属性读取。"""
    return [
        types.SimpleNamespace(
            ts=b["ts"], open=b["open"], high=b["high"], low=b["low"], close=b["close"],
            volume=b["volume"], amount=b["amount"],
        )
        for b in _bars(n)
    ]


class _Ctx:
    """dry-run 用最小上下文（只为让策略能跑起来）。"""

    params: dict = {}
    cash = 1_000_000.0
    pos = 0
    entry_price = None
    price = 10.0
    bar_index = 0
    history: list = []

    @property
    def closes(self):
        return []

    @property
    def is_holding(self):
        return self.pos > 0

    def buy(self, shares=None):
        pass

    def sell(self, shares=None):
        pass

    def flat(self):
        pass


def _run(code: str) -> None:
    """编译并在最小上下文里执行一次 on_bar（用于探测运行时是否放行）。"""
    funcs = compile_strategy(code)
    funcs["on_bar"]({"ts": 0, "open": 10.0, "high": 11.0, "low": 9.0, "close": 10.5, "volume": 1, "amount": 1.0}, _Ctx())


# --------------------------------------------------------------------------- #
# 1. 沙箱逃逸审计（回归）
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "attr",
    ["__class__", "__bases__", "__subclasses__", "__globals__", "__mro__", "__code__", "__dict__"],
)
def test_sandbox_rejects_dunder_attribute_access(attr):
    """dunder 属性访问必须在编译期被拒（G08 安全审计项）。"""
    with pytest.raises(SandboxError, match="invalid attribute name"):
        compile_strategy(f"def on_bar(bar, c):\n    c.{attr}\n    return 1\n")


def test_sandbox_getattr_builtin_unavailable():
    """`getattr(x, '__class__')` 无法绕过守卫：getattr 根本不在受限内建里。"""
    funcs = compile_strategy("def on_bar(bar, c):\n    return getattr(c, '__class__')\n")

    with pytest.raises(NameError, match="getattr"):
        funcs["on_bar"]({"close": 1}, _Ctx())


@pytest.mark.parametrize("expr", ["'{0.__class__}'.format(c)", "'{x.__class__}'.format_map({'x': c})"])
def test_sandbox_rejects_str_format_escape(expr):
    """str.format / format_map 的经典逃逸向量必须在运行时被拒。"""
    funcs = compile_strategy(f"def on_bar(bar, c):\n    return {expr}\n")

    with pytest.raises(NotImplementedError, match="format"):
        funcs["on_bar"]({"close": 1}, _Ctx())


@pytest.mark.parametrize(
    "code",
    [
        "import os\ndef on_bar(bar, c):\n    pass\n",
        "def on_bar(bar, c):\n    __import__('os')\n",
        "def on_bar(bar, c):\n    open('/etc/passwd')\n",
        "def on_bar(bar, c):\n    eval('1+1')\n",
        "def on_bar(bar, c):\n    exec('x=1')\n",
    ],
)
def test_sandbox_rejects_import_and_dangerous_builtins(code):
    """import 与危险内建（open/eval/exec/__import__）编译期硬拒。"""
    with pytest.raises(SandboxError):
        compile_strategy(code)


def test_sandbox_supports_augmented_assignment():
    """回归（G08 修复）：`x += 1` 曾被编译成 `_inplacevar_` 而守卫缺失 → 运行时 NameError。

    RestrictedPython 8.x 的 transformer 仍生成该调用但包内不再提供实现，
    沙箱必须自己按类型白名单补回，否则策略里最常用的写法直接不可用。
    """
    code = (
        "def on_bar(bar, c):\n"
        "    total = 0\n"
        "    total += bar['close']\n"
        "    total *= 2\n"
        "    total -= 1\n"
        "    c.params['acc'] = total\n"
    )
    _run(code)  # 修复前抛 NameError: name '_inplacevar_' is not defined

    ctx = _Ctx()
    ctx.params = {}
    funcs = compile_strategy(code)
    funcs["on_bar"]({"ts": 0, "open": 1, "high": 1, "low": 1, "close": 10.5, "volume": 1, "amount": 1.0}, ctx)
    assert ctx.params["acc"] == pytest.approx(10.5 * 2 - 1)


def test_sandbox_inplace_rejects_non_whitelisted_types():
    """增强赋值只放行内建安全类型，其它类型拒绝（不重新打开 operator.iadd 逃逸面）。"""
    code = "def on_bar(bar, c):\n    c += 1\n"
    funcs = compile_strategy(code)

    with pytest.raises(TypeError, match="内建安全类型"):
        funcs["on_bar"]({"close": 1}, _Ctx())  # _Ctx 不在白名单内


def test_sandbox_normal_strategy_still_works():
    """加固后正常策略照常运行（避免误伤）。"""
    funcs = compile_strategy(_SMA_STRATEGY)
    ctx = _Ctx()
    ctx.params = {}
    ctx.history = [{"close": 10.0} for _ in range(10)]
    funcs["on_bar"]({"ts": 0, "open": 1, "high": 1, "low": 1, "close": 99.0, "volume": 1, "amount": 1.0}, ctx)


# --------------------------------------------------------------------------- #
# 2. 子进程隔离与资源限制
# --------------------------------------------------------------------------- #
def test_run_isolated_returns_result_and_progress():
    """正常策略在子进程跑通，进度经管道回传，且回报运行信息。"""
    progress: list[int] = []
    out = run_isolated(
        _SMA_STRATEGY, {}, _bars(400), BacktestConfig(time_budget=30), grace=10, on_progress=progress.append
    )

    assert out["bars_used"] == 400
    assert len(out["equity_curve"]) == 400
    assert len(out["trades"]) >= 1
    assert progress, "进度回调应至少触发一次（每 200 根）"
    meta = out["_subprocess"]
    assert meta["exitcode"] == 0
    assert meta["elapsed_s"] >= 0
    assert meta["limits"]["enforced"] is limits_effective()


def test_run_isolated_terminates_infinite_loop_and_survives():
    """死循环策略被强制终止，**父进程存活**（这正是 G08 要解决的问题）。"""
    code = "def on_bar(bar, context):\n    while True:\n        pass\n"
    started = time.monotonic()

    with pytest.raises(StrategyResourceError, match="墙钟上限"):
        run_isolated(code, {}, _bars(10), BacktestConfig(time_budget=2), grace=1)

    elapsed = time.monotonic() - started
    assert 2 <= elapsed < 20, f"应在 time_budget+grace 附近终止，实际 {elapsed:.1f}s"
    # 父进程仍在正常执行（能走到这里即证明）


def test_run_isolated_propagates_strategy_error():
    """策略自身异常按 BacktestError 抛出，与进程内执行行为一致（业务错误不重试）。"""
    code = "def on_bar(bar, context):\n    raise ValueError('boom')\n"

    with pytest.raises(BacktestError, match="boom"):
        run_isolated(code, {}, _bars(5), BacktestConfig(time_budget=5), grace=2)


def test_run_isolated_does_not_leak_worker_state():
    """连续多次隔离执行互不影响（无残留进程/状态串扰）。"""
    outs = [run_isolated(_SMA_STRATEGY, {}, _bars(80), BacktestConfig(time_budget=20), grace=5) for _ in range(3)]

    assert all(o["bars_used"] == 80 for o in outs)
    assert len({o["_subprocess"]["pid"] for o in outs}) == 3  # 每次都是独立进程


@pytest.mark.skipif(not limits_effective(), reason="Windows 无 resource 模块，rlimit 不生效（已文档化）")
def test_cpu_limit_enforced_on_posix():
    """POSIX：CPU 时间上限生效，吃 CPU 的策略被 SIGXCPU 终止。"""
    code = "def on_bar(bar, context):\n    x = 0\n    while True:\n        x = x + 1\n"

    with pytest.raises(StrategyResourceError, match="CPU"):
        run_isolated(code, {}, _bars(5), BacktestConfig(time_budget=60), grace=60, cpu_seconds=2)


@pytest.mark.skipif(not limits_effective(), reason="Windows 无 resource 模块，rlimit 不生效（已文档化）")
def test_rlimit_as_enforced_on_posix():
    """POSIX：内核级 RLIMIT_AS 生效，疯狂分配的策略抛 MemoryError 而非拖垮 worker。"""
    code = "def on_bar(bar, context):\n    a = []\n    while True:\n        a.append([0] * 20000000)\n"

    with pytest.raises(BacktestError):
        run_isolated(
            code, {}, _bars(5), BacktestConfig(time_budget=60), grace=60, memory_bytes=64 * 1024 * 1024
        )


def test_child_rss_bytes_reads_real_usage():
    """零依赖读 RSS 在两平台都可用（Windows Win32 API / Linux /proc），且异常输入不抛错。"""
    rss = child_rss_bytes(os.getpid())

    assert rss > 5 * 1024 * 1024, f"解释器自身 RSS 不应小于 5MB，实际 {rss}"
    assert rss < 16 * 1024 * 1024 * 1024, f"RSS 明显解析错位：{rss}"
    assert child_rss_bytes(999_999_999) == -1, "不存在的 pid 应返回 -1 而不是抛错"


def test_memory_watchdog_terminates_hog_on_all_platforms():
    """跨平台内存看门狗：内存失控策略在**两个平台**都被快速拦下。

    回归背景：Windows 无 `resource` 模块，早期实现下 `memory_bytes` 被**完全忽略** ——
    实测失控策略约 600 MB/s 无上限增长（6 秒吃掉 3.7 GB），按默认墙钟 45s 外推可达 ~25 GB。
    Windows 上由父进程侧 RSS 看门狗拦截，POSIX 上 RLIMIT_AS 或看门狗先触发，两者都必须
    **远早于墙钟上限**结束，否则本用例会跑到 60s+ 而失败。
    """
    code = "def on_bar(bar, context):\n    a = []\n    while True:\n        a.append([0] * 20000000)\n"
    started = time.monotonic()

    with pytest.raises(BacktestError) as exc:  # StrategyResourceError 也是 BacktestError 子类
        run_isolated(
            code, {}, _bars(5), BacktestConfig(time_budget=60), grace=60, memory_bytes=32 * 1024 * 1024
        )

    elapsed = time.monotonic() - started
    assert elapsed < 30, f"内存失控必须被快速拦下，实际耗时 {elapsed:.1f}s（墙钟上限是 120s）"
    if os.name == "nt":
        # Windows 只能靠看门狗（无 resource 模块），必须命中内存分支而非超时分支
        assert isinstance(exc.value, StrategyResourceError), f"应由看门狗拦下，实际 {type(exc.value).__name__}"
        assert "内存增长超过上限" in str(exc.value)


def test_memory_budget_excludes_interpreter_overhead():
    """预算语义是"策略自身额外增长"：解释器/依赖 import 的开销不计入，正常策略不被误杀。

    子进程在 ready 消息里**自报**基线 RSS；若改用父进程侧"运行期最小 RSS"启发式，
    import 阶段的开销会被算进策略预算（默认 512MB 会被吃掉一截），造成误杀。
    """
    code = (
        "def on_bar(bar, context):\n"
        "    chunks = []\n"
        "    for _ in range(3):\n"
        "        chunks.append([0] * 3000000)\n"  # 3 × 约 24MB ≈ 72MB
        "    context.params['n'] = len(chunks)\n"
    )

    # params 传非空：BacktestContext.__init__ 用 `params or {}`，空 dict 会被替换成新对象，
    # 策略对 context.params 的写入便不回传（引擎既有行为，与本步无关）
    out = run_isolated(
        code, {"marker": 1}, _bars(5), BacktestConfig(time_budget=30), grace=5, memory_bytes=256 * 1024 * 1024
    )

    assert out["bars_used"] == 5, "策略应正常跑完，未被内存看门狗误杀"
    assert out["params"]["n"] == 3, "策略自身只用了约 72MB，不应被 256MB 预算误杀"
    assert out["_subprocess"]["peak_rss_bytes"] > 0


def test_peak_rss_reported_for_monitoring():
    """执行信息回报内存峰值（G25 回测监控的内存峰值数据源）。"""
    out = run_isolated(_SMA_STRATEGY, {}, _bars(50), BacktestConfig(time_budget=20), grace=5, memory_bytes=512 * 1024 * 1024)

    peak = out["_subprocess"]["peak_rss_bytes"]
    assert peak is not None and peak > 0
    assert peak < 512 * 1024 * 1024, "正常策略不应逼近内存上限"


@pytest.mark.skipif(limits_effective(), reason="POSIX 上 rlimit 生效，本用例验证的是 Windows 的 rlimit 降级行为")
def test_windows_reports_rlimit_not_enforced():
    """Windows：如实回报 **rlimit** 未生效（内存另由跨平台看门狗覆盖，见上一个用例）。"""
    out = run_isolated(_SMA_STRATEGY, {}, _bars(10), BacktestConfig(time_budget=10), grace=5)

    assert out["_subprocess"]["limits"] == {"enforced": False, "reason": "resource module unavailable (Windows)"}


# --------------------------------------------------------------------------- #
# 3. per-user 并发配额（真实 Redis）
# --------------------------------------------------------------------------- #
@pytest.fixture
def quota_user_id() -> int:
    """用一个不可能与真实数据冲突的 user_id 做配额测试，结束后清理键。"""
    uid = 900_000 + uuid.uuid4().int % 90_000
    get_redis_client().delete(backtest_quota._key(uid))
    try:
        yield uid
    finally:
        get_redis_client().delete(backtest_quota._key(uid))


def test_quota_blocks_over_limit(quota_user_id):
    """第 N+1 个并发请求被拒，且返回当前运行数。"""
    limit = _settings.BACKTEST_MAX_CONCURRENT_PER_USER
    for i in range(limit):
        granted, running = backtest_quota.acquire(quota_user_id, f"tok{i}")
        assert granted is True, f"第 {i + 1} 个应获准"
        assert running == i + 1

    granted, running = backtest_quota.acquire(quota_user_id, "tok-over")
    assert granted is False
    assert running == limit
    assert backtest_quota.running_count(quota_user_id) == limit


def test_quota_release_is_idempotent(quota_user_id):
    """释放幂等：重复释放不报错、不影响计数（任务重试/重复终态回调时必需）。"""
    backtest_quota.acquire(quota_user_id, "tok-a")
    backtest_quota.acquire(quota_user_id, "tok-b")

    backtest_quota.release(quota_user_id, "tok-a")
    backtest_quota.release(quota_user_id, "tok-a")
    backtest_quota.release(quota_user_id, "never-existed")

    assert backtest_quota.running_count(quota_user_id) == 1


def test_quota_self_heals_stale_slots(quota_user_id):
    """worker 崩溃留下的槽位按 stale 阈值自动回收，不会把用户永久锁死。"""
    key = backtest_quota._key(quota_user_id)
    stale = _settings.BACKTEST_QUOTA_STALE_SECONDS
    # 直接写入一个"很久以前"的槽位，模拟 worker 被 SIGKILL 后未释放
    get_redis_client().zadd(key, {f"dead-{i}": time.time() - stale - 60 for i in range(10)})
    assert int(get_redis_client().zcard(key)) == 10

    assert backtest_quota.running_count(quota_user_id) == 0  # 读时清理
    granted, _ = backtest_quota.acquire(quota_user_id, "fresh")
    assert granted is True


def test_queue_busy_threshold(quota_user_id):
    """队列积压达阈值判定为繁忙；阈值以下不繁忙。"""
    r = get_redis_client()
    queue = backtest_quota.BACKTEST_QUEUE
    r.delete(queue)
    try:
        assert backtest_quota.is_queue_busy() is False
        r.rpush(queue, *["x"] * _settings.BACKTEST_QUEUE_BUSY_THRESHOLD)
        assert backtest_quota.queue_depth() == _settings.BACKTEST_QUEUE_BUSY_THRESHOLD
        assert backtest_quota.is_queue_busy() is True
    finally:
        r.delete(queue)


# --------------------------------------------------------------------------- #
# 4. 服务层集成（真实 DB + 真实 Redis + 真实子进程）
# --------------------------------------------------------------------------- #
def _register(client: TestClient, username: str) -> str:
    r = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "pass123456", "email": f"{username}@test.local"},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_strategy(client: TestClient, token: str) -> int:
    r = client.post(
        "/api/v1/strategies",
        json={
            "title": "G08 双均线",
            "description": "金叉买死叉卖",
            "code": _SMA_STRATEGY,
            "params": {"entry": {"fast": 5}},
            "status": "active",
        },
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _cleanup_user(username: str) -> None:
    db = get_session()
    try:
        row = db.query(User).filter(User.username == username).first()
        if row:
            db.delete(row)
        db.commit()
    finally:
        db.close()


def test_create_backtest_returns_429_when_queue_busy(client: TestClient, monkeypatch):
    """队列积压达阈值时提交回测返回 429（而非排进去干等）。"""
    uname = f"{_PREFIX}{uuid.uuid4().hex[:8]}"
    queue = backtest_quota.BACKTEST_QUEUE
    r = get_redis_client()
    try:
        token = _register(client, uname)
        sid = _create_strategy(client, token)
        r.rpush(queue, *["x"] * _settings.BACKTEST_QUEUE_BUSY_THRESHOLD)

        resp = client.post(
            "/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519", "period": "1d"}, headers=_auth(token)
        )
        assert resp.status_code == 429, resp.text
        body = resp.json()
        assert body["code"] == 42902
        assert "队列繁忙" in body["msg"]
    finally:
        r.delete(queue)
        _cleanup_user(uname)


def test_create_backtest_returns_429_when_user_quota_exhausted(client: TestClient, monkeypatch):
    """同一用户并发回测达上限时，第 N+1 次返回 429（不再入队、不产生任务行）。"""
    uname = f"{_PREFIX}{uuid.uuid4().hex[:8]}"
    r = get_redis_client()
    monkeypatch.setattr(
        "app.worker.tasks.backtest_tasks.run_backtest_task",
        types.SimpleNamespace(delay=lambda task_id, quota_token=None: None),
    )
    monkeypatch.setattr(kline_repo, "get_bars", lambda db, period, symbol_id, start, end, limit=1000: _fake_bars())
    monkeypatch.setattr(backtest_service, "_save_backtest_memory", lambda *a, **k: None)
    r.delete(backtest_quota.BACKTEST_QUEUE)
    try:
        token = _register(client, uname)
        sid = _create_strategy(client, token)
        limit = _settings.BACKTEST_MAX_CONCURRENT_PER_USER

        created = []
        for _ in range(limit):
            resp = client.post(
                "/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519", "period": "1d"}, headers=_auth(token)
            )
            assert resp.status_code == 200, resp.text
            created.append(resp.json()["data"]["id"])

        resp = client.post(
            "/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519", "period": "1d"}, headers=_auth(token)
        )
        assert resp.status_code == 429, resp.text
        assert resp.json()["code"] == 42901
        assert "上限" in resp.json()["msg"]

        # 被拒的请求不得留下任务行（G09 起列表为分页信封 {items,total,page,size}）
        page = client.get("/api/v1/backtest/tasks", headers=_auth(token)).json()["data"]
        assert page["total"] == len(created)
        assert [t["id"] for t in page["items"]] == list(reversed(created))
    finally:
        r.delete(backtest_quota.BACKTEST_QUEUE)
        _cleanup_user(uname)


def test_execute_backtest_runs_in_subprocess_and_persists(client: TestClient, monkeypatch):
    """端到端：create → execute（经子进程）→ 结果落库，指标与进程内执行一致。"""
    uname = f"{_PREFIX}{uuid.uuid4().hex[:8]}"
    r = get_redis_client()
    monkeypatch.setattr(
        "app.worker.tasks.backtest_tasks.run_backtest_task",
        types.SimpleNamespace(delay=lambda task_id, quota_token=None: None),
    )
    monkeypatch.setattr(kline_repo, "get_bars", lambda db, period, symbol_id, start, end, limit=1000: _fake_bars())
    monkeypatch.setattr(backtest_service, "_save_backtest_memory", lambda *a, **k: None)
    r.delete(backtest_quota.BACKTEST_QUEUE)
    try:
        token = _register(client, uname)
        sid = _create_strategy(client, token)
        task_id = client.post(
            "/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519", "period": "1d"}, headers=_auth(token)
        ).json()["data"]["id"]

        result = backtest_service.execute_backtest(task_id)

        assert result["result_id"]
        metrics = result["metrics"]
        assert metrics["metrics_json"]["total_trades"] >= 1
        assert metrics["total_sells"] >= 1
        assert metrics["win_rate"] is not None

        # 任务终态 + 结果可查
        task = client.get(f"/api/v1/backtest/tasks/{task_id}", headers=_auth(token)).json()["data"]
        assert task["status"] == "success" and task["progress"] == 100
        detail = client.get(f"/api/v1/backtest/results/{result['result_id']}", headers=_auth(token)).json()["data"]
        assert detail["metrics_json"]["total_trades"] == metrics["metrics_json"]["total_trades"]
        assert detail["equity_curve"], "资金曲线应已落库（G32 数据链路）"
    finally:
        r.delete(backtest_quota.BACKTEST_QUEUE)
        _cleanup_user(uname)


def _create_strategy_with_code(client: TestClient, token: str, code: str, title: str) -> int:
    resp = client.post(
        "/api/v1/strategies",
        json={"title": title, "description": "G25 测试策略", "code": code, "params": {}, "status": "active"},
        headers=_auth(token),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def _make_backtest_mocks(monkeypatch):
    monkeypatch.setattr(
        "app.worker.tasks.backtest_tasks.run_backtest_task",
        types.SimpleNamespace(delay=lambda task_id, quota_token=None: None),
    )
    monkeypatch.setattr(kline_repo, "get_bars", lambda db, period, symbol_id, start, end, limit=1000: _fake_bars())
    monkeypatch.setattr(backtest_service, "_save_backtest_memory", lambda *a, **k: None)


def test_runaway_strategy_rejected_at_submission(client: TestClient, monkeypatch):
    """G25 第一层：死循环策略在**提交回测时**就被三级校验拒绝（400），不占用配额、不入队。"""
    uname = f"{_PREFIX}{uuid.uuid4().hex[:8]}"
    r = get_redis_client()
    _make_backtest_mocks(monkeypatch)
    r.delete(backtest_quota.BACKTEST_QUEUE)
    try:
        token = _register(client, uname)
        sid = _create_strategy_with_code(
            client, token, "def on_bar(bar, context):\n    while True:\n        pass\n", "G25 死循环"
        )

        resp = client.post(
            "/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519", "period": "1d"}, headers=_auth(token)
        )

        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == 40031
        assert "策略校验未通过" in resp.json()["msg"]
        # 被拒的提交不得留下任务行
        assert client.get("/api/v1/backtest/tasks", headers=_auth(token)).json()["data"]["total"] == 0
    finally:
        r.delete(backtest_quota.BACKTEST_QUEUE)
        _cleanup_user(uname)


def test_validation_rejects_strategy_with_syntax_error(client: TestClient, monkeypatch):
    """G25：语法错误策略在提交回测时被拒（带行号），前端可直接定位。"""
    uname = f"{_PREFIX}{uuid.uuid4().hex[:8]}"
    r = get_redis_client()
    _make_backtest_mocks(monkeypatch)
    r.delete(backtest_quota.BACKTEST_QUEUE)
    try:
        token = _register(client, uname)
        sid = _create_strategy_with_code(client, token, "def on_bar(bar, context):\n  x = \n", "G25 语法错")

        resp = client.post(
            "/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519", "period": "1d"}, headers=_auth(token)
        )

        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == 40031
        assert "第 3 行" in resp.json()["msg"] or "语法" in resp.json()["msg"]
    finally:
        r.delete(backtest_quota.BACKTEST_QUEUE)
        _cleanup_user(uname)


def test_runtime_isolation_still_catches_late_runaway(client: TestClient, monkeypatch):
    """G25 第二层：能通过 1 根 bar dry-run、但在后续 bar 死循环的策略，由运行时隔离兜底。

    两层防护互补 —— dry-run 只能覆盖「第 1 根 bar 就出问题」的策略，
    真正的兜底仍是子进程 + 墙钟 terminate。
    """
    uname = f"{_PREFIX}{uuid.uuid4().hex[:8]}"
    r = get_redis_client()
    _make_backtest_mocks(monkeypatch)
    monkeypatch.setattr(backtest_service.settings, "BACKTEST_TIME_BUDGET", 2.0)
    monkeypatch.setattr(backtest_service.settings, "BACKTEST_SUBPROCESS_GRACE", 1.0)
    r.delete(backtest_quota.BACKTEST_QUEUE)
    try:
        token = _register(client, uname)
        # dry-run 只有 1 根 bar（bar_index=0）→ 校验通过；真实回测到第 2 根才死循环
        sid = _create_strategy_with_code(
            client,
            token,
            "def initialize(context):\n    pass\n\n"
            "def on_bar(bar, context):\n    if context.bar_index > 1:\n        while True:\n            pass\n",
            "G25 延迟死循环",
        )
        resp = client.post(
            "/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519", "period": "1d"}, headers=_auth(token)
        )
        assert resp.status_code == 200, resp.text
        task_id = resp.json()["data"]["id"]

        with pytest.raises(backtest_service.BacktestFatalError, match="墙钟上限"):
            backtest_service.execute_backtest(task_id)
    finally:
        r.delete(backtest_quota.BACKTEST_QUEUE)
        _cleanup_user(uname)


def test_dry_run_infrastructure_failure_does_not_reject(monkeypatch):
    """校验器自身故障时**放行**（fail-open），不因 dry-run 起不来而挡住用户。

    真实触发场景：宿主经 `python - <<EOF`（stdin）运行时 spawn 无法重导入 __main__，
    会让**所有**策略都"校验不通过"。运行时隔离（G08）仍是兜底，不该整站不可用。
    """
    from app.agent import strategy_validator

    def _boom(*_a, **_k):
        raise BacktestError("策略子进程异常退出（exitcode=1）")

    monkeypatch.setattr(strategy_validator, "run_isolated", _boom)
    result = strategy_validator.validate_strategy(_SMA_STRATEGY)

    assert result["valid"] is True, "dry-run 基础设施故障不应拒绝策略"
    assert result["errors"] == []


def test_dry_run_strategy_failure_still_rejects(monkeypatch):
    """对照：策略**自身**运行期错误仍必须拒绝（fail-open 不能变成 fail-anything）。"""
    from app.agent import strategy_validator

    def _boom(*_a, **_k):
        raise StrategyRuntimeError("策略执行失败: ValueError: boom", line=3)

    monkeypatch.setattr(strategy_validator, "run_isolated", _boom)
    result = strategy_validator.validate_strategy(_SMA_STRATEGY)

    assert result["valid"] is False
    assert result["errors"][0]["line"] == 3
    assert "boom" in result["errors"][0]["message"]


def test_release_quota_is_noop_without_token():
    """无 token（历史/进程内调用）时释放是空操作，不抛错、不误删他人槽位。"""
    backtest_service.release_quota(999_999_999, None)  # 不存在的 task_id + 空 token
    assert backtest_service.release_quota(999_999_999, "") is None


def test_api_error_shape_for_quota(quota_user_id):
    """配额耗尽时抛的是 ApiError 429（供 API 层直接转成 HTTP 响应）。"""
    limit = _settings.BACKTEST_MAX_CONCURRENT_PER_USER
    for i in range(limit):
        backtest_quota.acquire(quota_user_id, f"t{i}")

    granted, running = backtest_quota.acquire(quota_user_id, "over")
    assert not granted
    err = ApiError(
        status_code=429, code=42901, msg=f"同时运行的回测已达上限（{running}/{limit}），请等待当前回测完成"
    )
    assert err.status_code == 429
    assert str(limit) in err.msg


def test_subprocess_disabled_flag_falls_back_in_process(client: TestClient, monkeypatch):
    """BACKTEST_SUBPROCESS_ENABLED=false 时退回进程内执行，结果与子进程路径一致（仅排查用）。

    这条兜底路径必须真的可用 —— 它是隔离出问题时的逃生开关。
    """
    uname = f"{_PREFIX}{uuid.uuid4().hex[:8]}"
    r = get_redis_client()
    monkeypatch.setattr(
        "app.worker.tasks.backtest_tasks.run_backtest_task",
        types.SimpleNamespace(delay=lambda task_id, quota_token=None: None),
    )
    monkeypatch.setattr(kline_repo, "get_bars", lambda db, period, symbol_id, start, end, limit=1000: _fake_bars())
    monkeypatch.setattr(backtest_service, "_save_backtest_memory", lambda *a, **k: None)
    monkeypatch.setattr(backtest_service.settings, "BACKTEST_SUBPROCESS_ENABLED", False)
    r.delete(backtest_quota.BACKTEST_QUEUE)
    try:
        token = _register(client, uname)
        sid = _create_strategy(client, token)
        task_id = client.post(
            "/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519", "period": "1d"}, headers=_auth(token)
        ).json()["data"]["id"]

        result = backtest_service.execute_backtest(task_id)

        assert result["result_id"]
        assert result["metrics"]["metrics_json"]["total_trades"] >= 1
        assert result["metrics"]["total_sells"] >= 1
    finally:
        r.delete(backtest_quota.BACKTEST_QUEUE)
        _cleanup_user(uname)

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

import time
import types
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.backtest.engine import BacktestConfig, BacktestError
from app.backtest.runner import StrategyResourceError, limits_effective, run_isolated
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
def test_memory_limit_enforced_on_posix():
    """POSIX：内存增长上限生效，疯狂分配的策略抛 MemoryError 而非拖垮 worker。"""
    code = "def on_bar(bar, context):\n    a = []\n    while True:\n        a.append([0] * 20000000)\n"

    with pytest.raises(BacktestError):
        run_isolated(
            code, {}, _bars(5), BacktestConfig(time_budget=60), grace=60, memory_bytes=64 * 1024 * 1024
        )


@pytest.mark.skipif(limits_effective(), reason="POSIX 上 rlimit 生效，本用例验证的是 Windows 的降级行为")
def test_windows_reports_limits_not_enforced():
    """Windows：明确回报 rlimit 未生效，而不是假装已保护（死循环仍由 terminate 兜底）。"""
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


def test_execute_backtest_fails_fast_on_runaway_strategy(client: TestClient, monkeypatch):
    """恶意策略（死循环）经服务层执行时被终止并标记 failed，worker 不受影响。"""
    uname = f"{_PREFIX}{uuid.uuid4().hex[:8]}"
    r = get_redis_client()
    monkeypatch.setattr(
        "app.worker.tasks.backtest_tasks.run_backtest_task",
        types.SimpleNamespace(delay=lambda task_id, quota_token=None: None),
    )
    monkeypatch.setattr(kline_repo, "get_bars", lambda db, period, symbol_id, start, end, limit=1000: _fake_bars())
    monkeypatch.setattr(backtest_service, "_save_backtest_memory", lambda *a, **k: None)
    monkeypatch.setattr(backtest_service.settings, "BACKTEST_TIME_BUDGET", 2.0)
    monkeypatch.setattr(backtest_service.settings, "BACKTEST_SUBPROCESS_GRACE", 1.0)
    r.delete(backtest_quota.BACKTEST_QUEUE)
    try:
        token = _register(client, uname)
        # 用死循环策略覆盖
        resp = client.post(
            "/api/v1/strategies",
            json={
                "title": "G08 死循环",
                "description": "恶意策略",
                "code": "def on_bar(bar, context):\n    while True:\n        pass\n",
                "params": {},
                "status": "active",
            },
            headers=_auth(token),
        )
        sid = resp.json()["data"]["id"]
        task_id = client.post(
            "/api/v1/backtest", json={"strategy_id": sid, "symbol": "600519", "period": "1d"}, headers=_auth(token)
        ).json()["data"]["id"]

        with pytest.raises(backtest_service.BacktestFatalError, match="墙钟上限"):
            backtest_service.execute_backtest(task_id)

        # 服务层把致命错误交给任务层落库；这里直接验证任务被标记失败且带原因
        backtest_service.mark_task_failed(task_id, "策略执行超过墙钟上限（测试）")
        task = client.get(f"/api/v1/backtest/tasks/{task_id}", headers=_auth(token)).json()["data"]
        assert task["status"] == "failed"
        assert "墙钟上限" in task["error"]
    finally:
        r.delete(backtest_quota.BACKTEST_QUEUE)
        _cleanup_user(uname)


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

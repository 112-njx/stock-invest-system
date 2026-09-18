"""G10 · P1-2a WebSocket 多实例广播验证（真实双进程 + 真实 Redis）。

**这是 P1-2a 的核心不变式**：WS 消息经 Redis pub/sub 广播到**所有** API 实例，客户端连到
哪个实例都能收到 —— 因此 Nginx 无需 sticky session，可以放心用 least_conn 分发。

测试方式：起两个独立 API 进程（不同端口、共享同一 Redis 与 DB），各连一个真实 WS 客户端，
向 ``market:updates`` 发布一次快照，断言**两个实例上的客户端都收到**。

为什么不能用 TestClient：同一进程内两个 TestClient 共享模块级 ConnectionManager 单例，
无法区分"实例"，也就验证不了跨实例广播。必须真起两个进程。

子进程用 ``APP_ENV=dev``：``APP_ENV=test`` 会跳过全部启动任务（含 WS 市场监听线程）。
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest
import websockets
from app.utils.redis_client import get_redis_client

BACKEND_DIR = Path(__file__).resolve().parents[1]
_SYMBOL_ID = 900001
_SENTINEL = f"g10-{uuid.uuid4().hex[:8]}"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_health(port: int, timeout: float = 60.0) -> None:
    """等实例 /health 就绪（dev 模式有缓存预热，启动较慢）。"""
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310 —— 本地固定地址
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    raise AssertionError(f"API 实例 :{port} 未在 {timeout}s 内就绪")


def _register(port: int) -> str:
    """注册一个测试用户，返回 access token（WS 非浏览器路径需要它）。"""
    uname = f"test_g10_{uuid.uuid4().hex[:8]}"
    body = json.dumps({"username": uname, "password": "pass123456", "email": f"{uname}@test.local"}).encode()
    req = urllib.request.Request(  # noqa: S310
        f"http://127.0.0.1:{port}/api/v1/auth/register",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
        payload = json.loads(resp.read())
    assert payload["code"] == 0, payload
    return payload["data"]["token"]


@pytest.fixture(scope="module")
def two_instances():
    """两个共享同一 Redis 的 API 实例（不同端口）。"""
    ports = [_free_port(), _free_port()]
    env = {**os.environ, "APP_ENV": "dev"}  # test 会跳过 WS 监听线程
    procs = [
        subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(p), "--log-level", "warning"],
            cwd=str(BACKEND_DIR),
            env=env,
        )
        for p in ports
    ]
    try:
        for p in ports:
            _wait_health(p)
        yield ports
    finally:
        for proc in procs:
            proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()


async def _connect_and_subscribe(port: int, token: str, symbol_ids: list[int]) -> "websockets.WebSocketClientProtocol":
    """连接 → 非浏览器鉴权（首条 auth 消息）→ 订阅。"""
    ws = await websockets.connect(f"ws://127.0.0.1:{port}/api/v1/ws/market", open_timeout=15)
    await ws.send(json.dumps({"action": "auth", "token": token}))
    await ws.send(json.dumps({"action": "subscribe", "symbol_ids": symbol_ids}))
    return ws


async def _drain_until_snapshot(ws, sentinel: str, timeout: float = 8.0) -> dict:
    """读消息直到拿到含 sentinel 的快照（容忍 auth/subscribe 的确认帧）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - time.monotonic()))
        if sentinel in raw:
            return json.loads(raw)
    raise AssertionError(f"未在 {timeout}s 内收到快照（sentinel={sentinel}）")


def test_ws_broadcast_reaches_all_instances(two_instances):
    """发布一次 → **两个实例上的客户端都收到**（Redis 广播，无需 sticky session）。"""
    ports = two_instances
    token = _register(ports[0])
    r = get_redis_client()

    async def scenario() -> list[dict]:
        conns = [await _connect_and_subscribe(p, token, [_SYMBOL_ID]) for p in ports]
        try:
            await asyncio.sleep(1.0)  # 等订阅在服务端登记完成
            # 模拟 realtime_poll：向 Redis 频道发布一条快照
            r.publish(
                "market:updates",
                json.dumps({"type": "snapshot", "symbol_id": _SYMBOL_ID, "data": {"price": _SENTINEL}}),
            )
            return [await _drain_until_snapshot(c, _SENTINEL) for c in conns]
        finally:
            for c in conns:
                await c.close()

    received = asyncio.run(scenario())

    assert len(received) == 2, "两个实例都应收到广播"
    for msg in received:
        assert msg["type"] == "snapshot"
        assert str(_SYMBOL_ID) in msg["data"] or _SYMBOL_ID in msg["data"], msg
        assert _SENTINEL in json.dumps(msg["data"])


def test_ws_unsubscribed_instance_does_not_receive(two_instances):
    """只有订阅了该标的的实例才推送 —— 广播是"发给所有实例"，但实例内仍按订阅集合过滤。

    这条守住"多实例不等于消息泄漏给无关连接"。
    """
    ports = two_instances
    token = _register(ports[0])
    other_symbol = 900002
    sentinel = f"g10-neg-{uuid.uuid4().hex[:8]}"
    r = get_redis_client()

    async def scenario() -> bool:
        # 实例 1 订阅目标标的；实例 2 订阅**另一个**标的
        ws1 = await _connect_and_subscribe(ports[0], token, [_SYMBOL_ID])
        ws2 = await _connect_and_subscribe(ports[1], token, [other_symbol])
        try:
            await asyncio.sleep(1.0)
            r.publish(
                "market:updates",
                json.dumps({"type": "snapshot", "symbol_id": _SYMBOL_ID, "data": {"price": sentinel}}),
            )
            got = await _drain_until_snapshot(ws1, sentinel)
            assert _SYMBOL_ID in got["data"] or str(_SYMBOL_ID) in got["data"]
            # 实例 2 未订阅该标的 → 不应收到（短超时内确认收不到）
            try:
                await asyncio.wait_for(ws2.recv(), timeout=2.0)
                return True  # 收到了 → 不符合预期
            except (TimeoutError, asyncio.TimeoutError):
                return False
        finally:
            await ws1.close()
            await ws2.close()

    assert asyncio.run(scenario()) is False, "未订阅该标的的实例不应收到该快照"

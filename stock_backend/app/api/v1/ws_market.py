"""实时行情 WebSocket：WS /api/v1/ws/market。

- JWT 鉴权：query 参数 token。
- 心跳：服务端每 15s 发 {"type":"ping"}，30s 无活动断开。
- 订阅：{"action":"subscribe","symbol_ids":[...]} / unsubscribe。
- 断线补拉：{"action":"sync","since":"ISO时间"} → 批量返回该时间后更新的快照。
- 增量推送：realtime_poll 写快照后经 Redis pub/sub 桥接，本进程市场监听器按订阅集合推送。
"""

import asyncio
import json
import logging
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token
from app.repositories import snapshot_repo
from app.utils.db import get_session
from app.ws.manager import ConnectionState, manager

logger = logging.getLogger(__name__)

router = APIRouter()

PING_INTERVAL = 15  # 秒：服务端心跳间隔
INACTIVE_TIMEOUT = 30  # 秒：超过该时长无任何消息（含 pong）则断开


@router.websocket("/api/v1/ws/market")
async def ws_market(ws: WebSocket, token: str = Query("")) -> None:
    user_id = decode_access_token(token)
    if user_id is None:
        await ws.close(code=4001, reason="unauthorized")
        return
    db = get_session()
    try:
        # 校验用户仍存在（token 有效但用户被删则拒绝）
        from app.repositories import user_repo

        if user_repo.get_by_id(db, user_id) is None:
            await ws.close(code=4001, reason="unauthorized")
            return
    finally:
        db.close()
    state = await manager.connect(user_id, ws)
    try:
        receive_task = asyncio.create_task(_receive_loop(state))
        ping_task = asyncio.create_task(_ping_loop(state))
        done, pending = await asyncio.wait({receive_task, ping_task}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            try:
                task.result()
            except Exception:  # noqa: BLE001
                pass
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(state)


async def _ping_loop(state: ConnectionState) -> None:
    """每 15s 发 ping；30s 无活动（未收到 pong/任何消息）则断开连接。"""
    while True:
        await asyncio.sleep(PING_INTERVAL)
        if (time.time() - state.last_activity.timestamp()) > INACTIVE_TIMEOUT:
            logger.info("[ws] heartbeat timeout, close user=%s", state.user_id)
            await state.ws.close(code=4000, reason="heartbeat timeout")
            return
        try:
            await state.ws.send_text(json.dumps({"type": "ping"}))
        except Exception:  # noqa: BLE001
            return


async def _receive_loop(state: ConnectionState) -> None:
    while True:
        raw = await state.ws.receive_text()
        state.last_activity = datetime.now(UTC)  # 任何消息（含 pong）视为活动
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            continue
        action = msg.get("action")
        if action == "subscribe":
            ids = [int(x) for x in msg.get("symbol_ids", []) if str(x).isdigit()]
            state.subscribed.update(ids)
        elif action == "unsubscribe":
            ids = [int(x) for x in msg.get("symbol_ids", []) if str(x).isdigit()]
            state.subscribed.difference_update(ids)
        elif action == "sync":
            await _handle_sync(state, msg.get("since"))


async def _handle_sync(state: ConnectionState, since: str) -> None:
    """断线增量补拉：查询 since 之后更新的快照，仅返回订阅范围内标的。"""
    from datetime import UTC, datetime

    if not since or not state.subscribed:
        return
    try:
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return
    db = get_session()
    try:
        updates = snapshot_repo.get_updated_after(db, since_dt)
    finally:
        db.close()
    data = {sid: d for sid, d in updates.items() if sid in state.subscribed}
    if data:
        await manager.send_to_user(state.user_id, {"type": "snapshot", "data": data})


# ---- 市场监听器（Redis pub/sub → 本进程 WS 推送）----
def dispatch_market_payload(loop: asyncio.AbstractEventLoop, payload: dict) -> None:
    """把 Redis market:updates 消息调度到 WS 推送协程（线程安全）。"""
    asyncio.run_coroutine_threadsafe(_dispatch(loop, payload), loop)


async def _dispatch(loop: asyncio.AbstractEventLoop, payload: dict) -> None:
    symbol_id = payload.get("symbol_id")
    kind = payload.get("type")
    if symbol_id is None:
        return
    if kind == "snapshot":
        await manager.broadcast_snapshots({int(symbol_id): payload.get("data", {})})
    elif kind == "kline":
        await manager.broadcast_kline(payload)


def _market_listener_loop(loop: asyncio.AbstractEventLoop) -> None:
    """后台线程：订阅 Redis market:updates，收到消息调度到 asyncio 主循环。"""
    import json as _json

    from app.utils.redis_client import get_redis_client

    pubsub = get_redis_client().pubsub()
    pubsub.subscribe("market:updates")
    logger.info("[ws] market listener started")
    while True:
        try:
            msg = pubsub.get_message(timeout=1.0, ignore_subscribe_messages=True)
            if msg and msg.get("type") == "message":
                payload = _json.loads(msg["data"])
                dispatch_market_payload(loop, payload)
        except Exception:  # noqa: BLE001
            logger.warning("[ws] market listener error, restarting pubsub", exc_info=True)
            try:
                pubsub.close()
                pubsub = get_redis_client().pubsub()
                pubsub.subscribe("market:updates")
            except Exception:  # noqa: BLE001
                pass

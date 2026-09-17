"""WebSocket 连接管理：多标签页连接、订阅集合、按订阅推送。

ConnectionManager 为进程内单例；realtime_poll 经 Redis pub/sub 桥接进入本进程后，
由市场监听器调用 broadcast_* 按订阅集合推送到对应连接。
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionState:
    """单条连接状态：用户、订阅集合、最近活动时间（心跳判活）、access token jti（黑名单复查）。"""

    __slots__ = ("user_id", "ws", "subscribed", "last_activity", "jti")

    def __init__(self, user_id: int, ws: WebSocket, jti: str | None = None) -> None:
        self.user_id = user_id
        self.ws = ws
        self.subscribed: set[int] = set()
        self.last_activity = datetime.now(UTC)
        self.jti = jti  # G29：心跳时复查黑名单，登出/踢出后及时断开


class ConnectionManager:
    """维护所有活跃连接（user_id → 连接列表，支持多标签页）及订阅集合。"""

    def __init__(self) -> None:
        self._connections: dict[int, list[ConnectionState]] = {}
        self._lock = asyncio.Lock()
        # G16：主事件循环引用，供同步上下文（Celery 任务/请求线程）跨线程调度 WS 推送
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """记录 uvicorn 主事件循环（应用启动时调用）。"""
        self._loop = loop

    def get_loop(self) -> asyncio.AbstractEventLoop | None:
        """获取主事件循环；未启动/已关闭时返回 None（调用方应静默跳过推送）。"""
        loop = self._loop
        if loop is None or loop.is_closed():
            return None
        return loop

    async def connect(self, user_id: int, ws: WebSocket, jti: str | None = None) -> ConnectionState:
        """accept 握手并注册连接（浏览器 Cookie 鉴权路径）。"""
        await ws.accept()
        return await self.register(user_id, ws, jti)

    async def register(self, user_id: int, ws: WebSocket, jti: str | None = None) -> ConnectionState:
        """仅注册已 accept 的连接（G29：首条 auth 消息兜底路径，握手已 accept）。"""
        state = ConnectionState(user_id, ws, jti)
        async with self._lock:
            self._connections.setdefault(user_id, []).append(state)
        logger.info("[ws] connect user=%s total=%d", user_id, self.count())
        return state

    async def disconnect(self, state: ConnectionState) -> None:
        async with self._lock:
            conns = self._connections.get(state.user_id, [])
            if state in conns:
                conns.remove(state)
            if not conns:
                self._connections.pop(state.user_id, None)
        logger.info("[ws] disconnect user=%s total=%d", state.user_id, self.count())

    def count(self) -> int:
        return sum(len(v) for v in self._connections.values())

    async def _send(self, state: ConnectionState, message: dict) -> None:
        try:
            await state.ws.send_text(json.dumps(message, ensure_ascii=False))
        except Exception:  # noqa: BLE001 连接已断开，清理
            await self.disconnect(state)

    async def send_to_user(self, user_id: int, message: dict) -> None:
        for state in list(self._connections.get(user_id, [])):
            await self._send(state, message)

    async def broadcast_all(self, message: dict) -> None:
        """向所有在线连接推送同一消息（G16：系统公告全局广播）。"""
        for conns in list(self._connections.values()):
            for state in list(conns):
                await self._send(state, message)

    async def broadcast_snapshots(self, updates: dict[int, dict]) -> None:
        """按订阅集合推送有更新的快照：{"type":"snapshot","data":{symbol_id:{...}}}。"""
        per_user: dict[int, dict[int, dict]] = {}
        for conns in list(self._connections.values()):
            for state in conns:
                hit = {sid: d for sid, d in updates.items() if sid in state.subscribed}
                if hit:
                    per_user.setdefault(state.user_id, {}).update(hit)
        for user_id, data in per_user.items():
            await self.send_to_user(user_id, {"type": "snapshot", "data": data})

    async def broadcast_kline(self, payload: dict) -> None:
        """推送新K线末根：{"type":"kline","symbol_id":...,"period":...,"bar":{...}}。"""
        symbol_id = payload.get("symbol_id")
        for conns in list(self._connections.values()):
            for state in conns:
                if symbol_id in state.subscribed:
                    await self._send(
                        state,
                        {
                            "type": "kline",
                            "symbol_id": symbol_id,
                            "period": payload.get("period"),
                            "bar": payload.get("bar", {}),
                        },
                    )


manager = ConnectionManager()

"""AI 聊天 API：SSE 流式对话（阶段五 5.1：keepalive 心跳）。"""

import asyncio
import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agent import chat_service
from app.agent.sse import read_deltas_after, read_done
from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.models.user import User
from app.repositories import conversation_repo

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
settings = get_settings()


class ChatIn(BaseModel):
    conversation_id: int | None = Field(None, description="会话ID（空则新建）")
    symbol: str | None = Field(None, description="绑定标的（代码或 symbol_id，可选）")
    content: str = Field(..., min_length=1, description="用户输入")
    agent_id: int | None = Field(None, description="定制 Agent ID（3.7，可选）")
    run_type: str = Field("custom", description="diagnostic/plan/radar/strategy/custom")


async def _sse_keepalive(gen):
    """包装事件流：空闲超过 SSE_KEEPALIVE_INTERVAL 秒时发送注释行 `:keepalive`。

    采用 asyncio.Queue + 后台 keeper 任务，避免对 `anext` 使用 wait_for 取消在途生成。
    """
    queue: asyncio.Queue = asyncio.Queue()

    async def producer():
        async for ev in gen:
            await queue.put(("data", ev))
        await queue.put(("end", None))

    async def keeper():
        while True:
            await asyncio.sleep(settings.SSE_KEEPALIVE_INTERVAL)
            await queue.put(("keepalive", None))

    ptask = asyncio.create_task(producer())
    ktask = asyncio.create_task(keeper())
    try:
        while True:
            kind, ev = await queue.get()
            if kind == "data":
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            elif kind == "keepalive":
                yield ":keepalive\n\n"
            elif kind == "end":
                break
    finally:
        ktask.cancel()
        if not ptask.done():
            ptask.cancel()


@router.post("")
async def chat(payload: ChatIn, current: User = Depends(get_current_user)) -> StreamingResponse:
    async def event_source():
        gen = chat_service.stream_chat(
            user_id=current.id,
            conversation_id=payload.conversation_id,
            symbol=payload.symbol,
            content=payload.content,
            agent_id=payload.agent_id,
            run_type=payload.run_type,
        )
        async for frame in _sse_keepalive(gen):
            yield frame

    return StreamingResponse(event_source(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/resume")
async def chat_resume(
    conversation_id: int = Query(..., description="会话ID"),
    last_seq: int = Query(0, ge=0, description="已收到的最后 seq，补发 seq>last_seq 的 delta"),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """断点续传：从 Redis 缓存补发 seq>last_seq 的 delta，缓存过期则返回 resync 提示。

    阶段五 5.2：流式中断后前端带 last_seq 重连，后端从 `chat_delta:{conversation_id}` 补发，
    不重复不丢失；缓存已过期（TTL 600s）返回 `{"type":"resync"}` 提示重新加载完整消息。
    """
    if conversation_repo.get_conversation(db, current.id, conversation_id) is None:
        raise ApiError(status_code=404, code=40410, msg="会话不存在")

    async def event_source():
        deltas = read_deltas_after(conversation_id, last_seq)
        if deltas is None:
            yield "data: " + json.dumps({"type": "resync", "conversation_id": conversation_id}, ensure_ascii=False) + "\n\n"
            return
        for d in deltas:
            yield "data: " + json.dumps(d, ensure_ascii=False) + "\n\n"
        done = read_done(conversation_id)
        if done is not None:
            yield "data: " + json.dumps(done, ensure_ascii=False) + "\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

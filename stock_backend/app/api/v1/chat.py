"""AI 聊天 API：SSE 流式对话（3.2/3.3 集成点，多智能体/记忆在 3.4/3.8 增强）。"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent import chat_service
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class ChatIn(BaseModel):
    conversation_id: int | None = Field(None, description="会话ID（空则新建）")
    symbol: str | None = Field(None, description="绑定标的（代码或 symbol_id，可选）")
    content: str = Field(..., min_length=1, description="用户输入")
    agent_id: int | None = Field(None, description="定制 Agent ID（3.7，可选）")
    run_type: str = Field("custom", description="diagnostic/plan/radar/strategy/custom")


@router.post("")
async def chat(payload: ChatIn, current: User = Depends(get_current_user)) -> StreamingResponse:
    async def event_source():
        async for ev in chat_service.stream_chat(
            user_id=current.id,
            conversation_id=payload.conversation_id,
            symbol=payload.symbol,
            content=payload.content,
            agent_id=payload.agent_id,
            run_type=payload.run_type,
        ):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

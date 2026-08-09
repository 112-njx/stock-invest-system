"""会话与消息响应模型（统一由 {code, msg, data} 包裹）。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreateIn(BaseModel):
    title: str | None = Field(None, max_length=128, description="会话标题，默认「新会话」")


class ConversationRenameIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=128, description="新标题")


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class MessageCreateIn(BaseModel):
    role: Literal["user", "assistant", "system"] = "user"
    content: str = Field(..., min_length=1, description="消息内容")
    symbol: str | None = Field(None, description="绑定标的（代码或 symbol_id，可选）")
    tokens: int | None = Field(None, ge=0)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversation_id: int
    role: str
    symbol_id: int | None = None
    content: str
    tokens: int | None = None
    created_at: datetime

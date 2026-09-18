"""会话与消息 API：创建/列表/重命名/删除会话、追加/拉取消息。

P1-6a（G09）：列表端点统一 `page/size` 分页信封；消息端点改**游标分页**
（`limit`/`before`），避免长会话一次返回 MB 级响应体。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import ok
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreateIn,
    ConversationOut,
    ConversationRenameIn,
    MessageCreateIn,
    MessageOut,
)
from app.schemas.pagination import (
    DEFAULT_MESSAGE_LIMIT,
    MAX_MESSAGE_LIMIT,
    PageParams,
    cursor_envelope,
    page_envelope,
)
from app.services import conversation_service

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


@router.post("")
def create_conversation(
    payload: ConversationCreateIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    conv = conversation_service.create_conversation(db, current.id, payload.title)
    return ok(data=ConversationOut.model_validate(conv).model_dump(mode="json"), msg="创建成功")


@router.get("")
def list_conversations(
    params: PageParams = Depends(),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows, total = conversation_service.list_conversations(db, current.id, page=params.page, size=params.size)
    items = [ConversationOut.model_validate(c).model_dump(mode="json") for c in rows]
    return ok(data=page_envelope(items, total, params.page, params.size))


@router.patch("/{conversation_id}")
def rename_conversation(
    conversation_id: int,
    payload: ConversationRenameIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    conv = conversation_service.rename_conversation(db, current.id, conversation_id, payload.title)
    return ok(data=ConversationOut.model_validate(conv).model_dump(mode="json"), msg="重命名成功")


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    conversation_service.delete_conversation(db, current.id, conversation_id)
    return ok(msg="删除成功")


@router.post("/{conversation_id}/messages")
def add_message(
    conversation_id: int,
    payload: MessageCreateIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    msg = conversation_service.add_message(
        db, current.id, conversation_id, payload.role, payload.content, payload.symbol, payload.tokens
    )
    return ok(data=MessageOut.model_validate(msg).model_dump(mode="json"), msg="发送成功")


@router.get("/{conversation_id}/messages")
def list_messages(
    conversation_id: int,
    limit: int = Query(DEFAULT_MESSAGE_LIMIT, ge=1, le=MAX_MESSAGE_LIMIT, description="本页条数，默认 50，最大 200"),
    before: int | None = Query(None, ge=1, description="游标：上一页最旧一条的 message_id；不传取最新一页"),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows, has_more = conversation_service.list_messages(
        db, current.id, conversation_id, limit=limit, before=before
    )
    items = [MessageOut.model_validate(m).model_dump(mode="json") for m in rows]
    # next_cursor = 本页最旧一条的 id（更早一页的游标）；无更早消息时为 null
    next_cursor = rows[0].id if (has_more and rows) else None
    return ok(data=cursor_envelope(items, has_more, next_cursor))

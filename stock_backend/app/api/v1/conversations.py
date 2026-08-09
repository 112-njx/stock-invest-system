"""会话与消息 API：创建/列表/重命名/删除会话、追加/拉取消息。"""

from fastapi import APIRouter, Depends
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
def list_conversations(current: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    rows = conversation_service.list_conversations(db, current.id)
    return ok(data=[ConversationOut.model_validate(c).model_dump(mode="json") for c in rows])


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
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rows = conversation_service.list_messages(db, current.id, conversation_id)
    return ok(data=[MessageOut.model_validate(m).model_dump(mode="json") for m in rows])

"""会话与消息读写：conversations / chat_messages。

多租户隔离（借鉴 QuantDinger）：所有查询强制带 user_id 过滤，防止越权。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.strategy import ChatMessage, Conversation


# ---- conversations ----
def create_conversation(db: Session, user_id: int, title: str) -> Conversation:
    conv = Conversation(user_id=user_id, title=title)
    db.add(conv)
    db.flush()
    return conv


def list_conversations(db: Session, user_id: int) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.updated_at.desc())
        )
    )


def get_conversation(db: Session, user_id: int, conv_id: int) -> Conversation | None:
    return db.scalar(select(Conversation).where(Conversation.id == conv_id, Conversation.user_id == user_id))


def rename_conversation(db: Session, user_id: int, conv_id: int, title: str) -> Conversation | None:
    conv = get_conversation(db, user_id, conv_id)
    if conv is None:
        return None
    conv.title = title
    db.flush()
    return conv


def delete_conversation(db: Session, user_id: int, conv_id: int) -> bool:
    conv = get_conversation(db, user_id, conv_id)
    if conv is None:
        return False
    db.delete(conv)  # chat_messages 级联删除（FK ON DELETE CASCADE）
    db.flush()
    return True


# ---- chat_messages ----
def add_message(
    db: Session,
    conversation_id: int,
    role: str,
    content: str,
    symbol_id: int | None = None,
    tokens: int | None = None,
) -> ChatMessage:
    msg = ChatMessage(conversation_id=conversation_id, role=role, content=content, symbol_id=symbol_id, tokens=tokens)
    db.add(msg)
    db.flush()
    return msg


def list_messages(db: Session, conversation_id: int) -> list[ChatMessage]:
    """按会话拉取消息（时间升序，稳定顺序）。"""
    return list(
        db.scalars(
            select(ChatMessage).where(ChatMessage.conversation_id == conversation_id).order_by(ChatMessage.created_at, ChatMessage.id)
        )
    )

"""会话与消息读写：conversations / chat_messages。

多租户隔离（借鉴 QuantDinger）：所有查询强制带 user_id 过滤，防止越权。
"""

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.strategy import ChatMessage, Conversation


# ---- conversations ----
def create_conversation(db: Session, user_id: int, title: str) -> Conversation:
    conv = Conversation(user_id=user_id, title=title)
    db.add(conv)
    db.flush()
    return conv


def list_conversations(
    db: Session, user_id: int, offset: int | None = None, limit: int | None = None
) -> list[Conversation]:
    """会话列表（更新时间倒序）。offset/limit 为 None 时不限（供内部全量调用）。"""
    stmt = select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.updated_at.desc())
    if offset is not None:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))


def count_conversations(db: Session, user_id: int) -> int:
    stmt = select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id)
    return int(db.scalar(stmt) or 0)


def get_conversation(db: Session, user_id: int, conv_id: int) -> Conversation | None:
    return db.scalar(select(Conversation).where(Conversation.id == conv_id, Conversation.user_id == user_id))


def rename_conversation(db: Session, user_id: int, conv_id: int, title: str) -> Conversation | None:
    conv = get_conversation(db, user_id, conv_id)
    if conv is None:
        return None
    conv.title = title
    db.flush()
    return conv


def update_summary(db: Session, conv_id: int, summary: str) -> None:
    """更新会话摘要（阶段八 8.1，异步任务调用）。"""
    conv = db.get(Conversation, conv_id)
    if conv is not None:
        conv.summary = summary
        db.flush()


def update_title(db: Session, conv_id: int, title: str) -> None:
    """更新会话标题（阶段八 8.7，异步任务调用）。"""
    conv = db.get(Conversation, conv_id)
    if conv is not None:
        conv.title = title
        db.flush()


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
    """按会话拉取**全量**消息（时间升序，稳定顺序）。

    注意：仅供内部链路使用（LLM 上下文组装、会话摘要）。对外端点走 `list_messages_page`，
    避免长会话一次返回 MB 级响应体。
    """
    return list(
        db.scalars(
            select(ChatMessage).where(ChatMessage.conversation_id == conversation_id).order_by(ChatMessage.created_at, ChatMessage.id)
        )
    )


def get_message(db: Session, conversation_id: int, message_id: int) -> ChatMessage | None:
    """按 id 取会话内单条消息（游标分页定位用）。"""
    return db.scalar(
        select(ChatMessage).where(ChatMessage.id == message_id, ChatMessage.conversation_id == conversation_id)
    )


def list_messages_page(
    db: Session, conversation_id: int, limit: int, before: ChatMessage | None = None
) -> tuple[list[ChatMessage], bool]:
    """消息游标分页（P1-6a）：取窗口内**最新** limit 条，返回 (升序 items, has_more)。

    - `before` 为游标消息（更早的一页从这里往前取），None 表示取最新一页。
    - 排序键为 (created_at, id)，游标过滤用双分支条件而非行值比较
      （`(a,b) < (c,d)` 在 SQLite 测试库不被支持）。
    """
    stmt = select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
    if before is not None:
        stmt = stmt.where(
            or_(
                ChatMessage.created_at < before.created_at,
                and_(ChatMessage.created_at == before.created_at, ChatMessage.id < before.id),
            )
        )
    # 多取一条用于判断是否还有更早的消息
    rows = list(db.scalars(stmt.order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc()).limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]
    rows.reverse()  # 对外统一升序（与全量接口一致）
    return rows, has_more


def count_messages(db: Session, conversation_id: int) -> int:
    """会话消息条数（阶段八 8.1 摘要触发判定）。"""
    stmt = select(func.count()).select_from(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
    return int(db.scalar(stmt) or 0)

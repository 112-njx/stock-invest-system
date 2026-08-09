"""会话与消息服务：创建/列表/重命名/删除、追加消息、按会话拉取。"""

from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.models.strategy import ChatMessage, Conversation
from app.models.symbol import Symbol
from app.repositories import conversation_repo, symbol_repo


def create_conversation(db: Session, user_id: int, title: str | None) -> Conversation:
    conv = conversation_repo.create_conversation(db, user_id, title or "新会话")
    db.commit()
    db.refresh(conv)
    return conv


def list_conversations(db: Session, user_id: int) -> list[Conversation]:
    return conversation_repo.list_conversations(db, user_id)


def _get_owned(db: Session, user_id: int, conv_id: int) -> Conversation:
    conv = conversation_repo.get_conversation(db, user_id, conv_id)
    if conv is None:
        raise ApiError(status_code=404, code=40410, msg="会话不存在")
    return conv


def rename_conversation(db: Session, user_id: int, conv_id: int, title: str) -> Conversation:
    conv = _get_owned(db, user_id, conv_id)
    conv.title = title
    db.commit()
    db.refresh(conv)
    return conv


def delete_conversation(db: Session, user_id: int, conv_id: int) -> None:
    if not conversation_repo.delete_conversation(db, user_id, conv_id):
        raise ApiError(status_code=404, code=40410, msg="会话不存在")
    db.commit()


def _strict_symbol_id(db: Session, symbol: str) -> int:
    """严格解析标的：代码或 id 必须存在于 symbols，否则 400（消息绑定要求真实标的）。"""
    sym = symbol_repo.get_by_code(db, symbol)
    if sym:
        return sym.id
    if symbol.isdigit():
        sym = db.get(Symbol, int(symbol))
        if sym:
            return sym.id
    raise ApiError(status_code=400, code=40002, msg=f"标的不存在: {symbol}")


def add_message(db: Session, user_id: int, conv_id: int, role: str, content: str, symbol: str | None, tokens: int | None) -> ChatMessage:
    conv = _get_owned(db, user_id, conv_id)
    symbol_id = _strict_symbol_id(db, symbol) if symbol else None
    msg = conversation_repo.add_message(db, conv.id, role, content, symbol_id=symbol_id, tokens=tokens)
    db.commit()
    db.refresh(msg)
    return msg


def list_messages(db: Session, user_id: int, conv_id: int) -> list[ChatMessage]:
    _get_owned(db, user_id, conv_id)
    return conversation_repo.list_messages(db, conv_id)

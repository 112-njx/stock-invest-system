"""G14（P0-2）：用户自填 API Key 的校验、存取与 LLMService 装配。

- **加密存储**：复用 G15 的 AES-256-GCM（`models.types.EncryptedText`），明文永不落库。
- **格式校验**：DeepSeek Key 形如 `sk-` + 32 位以上字母数字；只做基本形态校验（不做联网验证）。
- **优先级**：用户自填 key 优先，未填回退服务端默认 key。
- **用量统计**：每次调用结束把 (prompt, completion) token 累加到 users 表（估算值，非精确计费）。
"""

import logging
import re

from sqlalchemy.orm import Session

from app.services.llm.llm_service import LLMService, get_llm_service

logger = logging.getLogger(__name__)

# DeepSeek Key 形态：sk- 前缀 + 32 位以上 [A-Za-z0-9]
API_KEY_PREFIX = "sk-"
_API_KEY_RE = re.compile(r"^sk-[A-Za-z0-9_-]{32,}$")
API_KEY_MAX_LEN = 128


class ApiKeyFormatError(ValueError):
    """API Key 格式不合法（供 API 层转 400）。"""


def validate_api_key(raw: str) -> str:
    """校验并归一化用户填写的 Key；不合法抛 ApiKeyFormatError。"""
    key = (raw or "").strip()
    if not key:
        raise ApiKeyFormatError("API Key 不能为空")
    if len(key) > API_KEY_MAX_LEN:
        raise ApiKeyFormatError(f"API Key 长度不能超过 {API_KEY_MAX_LEN} 字符")
    if not key.startswith(API_KEY_PREFIX):
        raise ApiKeyFormatError(f"API Key 格式不正确，应以 {API_KEY_PREFIX} 开头")
    if not _API_KEY_RE.match(key):
        raise ApiKeyFormatError("API Key 格式不正确，请检查是否复制完整")
    return key


def get_user_api_key(db: Session, user_id: int) -> str | None:
    """取用户自填 Key 明文（ORM 层自动解密）；未填返回 None。"""
    from app.repositories import user_repo

    user = user_repo.get_by_id(db, user_id)
    if user is None or not user.api_key_encrypted:
        return None
    return user.api_key_encrypted


def record_usage(db: Session, user_id: int, prompt_tokens: int, completion_tokens: int) -> None:
    """累计 token 用量（best-effort，失败只告警不影响对话）。"""
    if prompt_tokens <= 0 and completion_tokens <= 0:
        return
    from app.repositories import user_repo

    try:
        user_repo.add_llm_tokens(db, user_id, prompt_tokens, completion_tokens)
        db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("record llm usage failed user=%s: %s", user_id, e)
        db.rollback()


def build_llm_service_for_user(db: Session, user_id: int, base: LLMService | None = None) -> LLMService:
    """装配该用户的 LLMService：用户 key 优先 + token 用量累加回调。

    `base` 为进程级单例（调用方传入以保留测试注入缝隙）；用量回调使用**独立会话**
    （`SessionLocal`），避免与请求会话的事务/生命周期耦合 —— 流式对话的用量在流结束时
    才产生，此时请求会话可能已进入收尾。

    测试替身（无 `with_api_key`）原样返回，不做 key 装配与用量统计。
    """
    from app.utils.db import SessionLocal

    base = base or get_llm_service()
    if not hasattr(base, "with_api_key"):
        return base

    def _sink(prompt_tokens: int, completion_tokens: int, estimated: bool) -> None:
        s = SessionLocal()
        try:
            record_usage(s, user_id, prompt_tokens, completion_tokens)
        finally:
            s.close()

    try:
        key = get_user_api_key(db, user_id)
    except Exception as e:  # noqa: BLE001 — 解密失败（密钥轮换等）不应中断对话
        logger.warning("load user api key failed user=%s: %s", user_id, e)
        key = None
    return base.with_api_key(key, usage_sink=_sink) if key else _with_sink(base, _sink)


def _with_sink(svc: LLMService, sink) -> LLMService:
    """无用户 key 时也要统计用量（用服务端 key 的调用同样计入用户成本视图）。"""
    return LLMService(
        provider=svc.provider,
        breaker=svc.breaker,
        bucket=svc.bucket,
        usage_sink=sink,
    )

"""G15（P0-3a）本地加密工具：AES-256-GCM（认证加密，密文自带完整性校验）。

- 密钥从环境变量 `MEMORY_ENCRYPTION_KEY` 读取，**禁止硬编码**。取值支持 64 位 hex（32 字节）
  或 32 字节原始字符串；长度不符直接报错而非降级。
  生成方式：``python -c "import secrets; print(secrets.token_hex(32))"``
- 密文格式：``b"ENC1"`` + nonce(12) + AESGCM 输出（密文 ‖ tag16）。
  4 字节魔数用于区分密文与存量明文 —— 迁移期 `data/memory/` 下已有明文 .md，读取时自动兼容。
- 密钥未配置时 `get_key()` 抛 `EncryptionKeyMissing`，**不静默降级为明文**（避免误以为已加密）。
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

MAGIC = b"ENC1"  # 密文文件头（4 字节）
NONCE_LEN = 12  # AES-GCM 推荐 96 位 nonce
KEY_LEN = 32  # AES-256


class EncryptionKeyMissing(RuntimeError):
    """MEMORY_ENCRYPTION_KEY 未配置（需人工配置，禁止硬编码兜底）。"""


class EncryptionError(RuntimeError):
    """密钥格式错误 / 解密失败（密钥不匹配或数据损坏）。"""


def _decode_key(raw: str) -> bytes:
    """解析密钥字符串：优先按 64 位 hex，否则按原始字节（须 32 字节）。"""
    raw = (raw or "").strip()
    if not raw:
        raise EncryptionKeyMissing(
            "MEMORY_ENCRYPTION_KEY 未配置：请生成 32 字节随机密钥并写入环境变量/.env —— "
            'python -c "import secrets; print(secrets.token_hex(32))"'
        )
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        key = raw.encode("utf-8")
    if len(key) != KEY_LEN:
        raise EncryptionError(f"密钥必须 {KEY_LEN} 字节（64 位 hex），当前 {len(key)} 字节")
    return key


@lru_cache(maxsize=8)
def _cached_key(raw: str) -> bytes:
    return _decode_key(raw)


def get_key() -> bytes:
    """当前配置的密钥（按取值缓存，配置变更自动重新解析）。"""
    return _cached_key(settings.MEMORY_ENCRYPTION_KEY or "")


def is_configured() -> bool:
    """密钥是否已正确配置（供启动自检 / 健康检查用，不抛异常）。"""
    try:
        get_key()
        return True
    except (EncryptionKeyMissing, EncryptionError):
        return False


def is_encrypted(blob: bytes) -> bool:
    """是否为本模块产出的密文（用于存量明文兼容读取）。"""
    return bool(blob) and blob[: len(MAGIC)] == MAGIC


def encrypt_bytes(data: bytes) -> bytes:
    """加密：返回 ``MAGIC + nonce + ciphertext‖tag``。"""
    key = get_key()
    nonce = os.urandom(NONCE_LEN)
    return MAGIC + nonce + AESGCM(key).encrypt(nonce, data, None)


def decrypt_bytes(blob: bytes) -> bytes:
    """解密；非本模块密文（存量明文）原样返回，保证迁移期可读。"""
    if not is_encrypted(blob):
        return blob
    key = get_key()
    nonce = blob[len(MAGIC) : len(MAGIC) + NONCE_LEN]
    payload = blob[len(MAGIC) + NONCE_LEN :]
    try:
        return AESGCM(key).decrypt(nonce, payload, None)
    except Exception as e:  # noqa: BLE001 — InvalidTag 等统一归类
        raise EncryptionError("解密失败：密钥不匹配或数据损坏") from e


def encrypt_text(text: str) -> bytes:
    return encrypt_bytes(text.encode("utf-8"))


def decrypt_text(blob: bytes) -> str:
    return decrypt_bytes(blob).decode("utf-8")


# ---- 文本列形态（G34：memory_chunks.content 等 Text 列，密文以 base64 文本落库）----
def encrypt_str(text: str) -> str:
    """加密为可存 Text 列的 ASCII 串：``base64(MAGIC ‖ nonce ‖ ct‖tag)``。"""
    return base64.b64encode(encrypt_bytes(text.encode("utf-8"))).decode("ascii")


def decrypt_str(value: str) -> str:
    """解密 Text 列；**非本模块密文（存量明文行）原样返回**，保证迁移期可读。"""
    if not value:
        return value
    try:
        blob = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return value  # 非 base64 → 存量明文
    if not is_encrypted(blob):
        return value  # base64 但无魔数 → 存量明文
    return decrypt_bytes(blob).decode("utf-8")

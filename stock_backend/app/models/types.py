"""自定义 SQLAlchemy 列类型（G34 · P0-3b）。

`EncryptedText`：Text 列落库自动 AES-256-GCM 加密、读取自动解密。用 TypeDecorator 而非在各
读写点手工加解密，好处是**所有读取方（API / 导出 / 脚本 / 后台任务）零改动即拿到明文**，
不会漏掉某个出口而把密文吐给用户。

注意：加密后无法在 SQL 层对内容做比较/排序/LIKE（密文每次加密结果不同）。当前 memory_chunks.content
仅用于整行读写，无 SQL 层过滤，故安全。若将来需要按内容检索，请改走 embedding 向量检索。
"""

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core import crypto


class EncryptedText(TypeDecorator):
    """AES-256-GCM 加密的 Text 列（密文以 base64 文本落库，列类型不变，无需迁移）。"""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return crypto.encrypt_str(str(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return crypto.decrypt_str(value)

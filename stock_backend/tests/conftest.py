"""pytest 公共夹具。"""

import os
import secrets

os.environ.setdefault("APP_ENV", "test")  # 测试环境：跳过启动预热/调度任务
os.environ["EMBEDDING_MODEL"] = "hash"  # 测试强制用 hash embedding（避免下载 MiniLM 模型，确定性）
# G15/G34：测试用一次性随机密钥（32 字节），使测试自包含、不依赖本机 .env 密钥
os.environ.setdefault("MEMORY_ENCRYPTION_KEY", secrets.token_hex(32))

import pytest  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c

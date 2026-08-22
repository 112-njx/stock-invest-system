"""pytest 公共夹具。"""

import os

os.environ.setdefault("APP_ENV", "test")  # 测试环境：跳过启动预热/调度任务
os.environ["EMBEDDING_MODEL"] = "hash"  # 测试强制用 hash embedding（避免下载 MiniLM 模型，确定性）

import pytest  # noqa: E402
from app.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c

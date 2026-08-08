"""pytest 公共夹具。"""

import pytest
from app.main import app
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c

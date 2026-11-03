import pytest
from fastapi.testclient import TestClient

from kiln_api.config import Settings
from kiln_api.enums import Environment
from kiln_api.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(env=Environment.TEST)))

from fastapi.testclient import TestClient
import pytest
from app.main import app
from uuid import uuid4


def _random_credentials(username: str | None = None) -> dict[str, str]:
    suffix = uuid4().hex
    generated_username = username or f"user_{suffix[:12]}"
    password = f"Aa1{suffix[:12]}"
    email = f"{generated_username}_{suffix[12:18]}@example.com"
    return {
        "email": email,
        "password": password,
        "username": generated_username,
    }


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def credentials_factory():
    def _factory(*, username: str | None = None) -> dict[str, str]:
        return _random_credentials(username=username)

    return _factory

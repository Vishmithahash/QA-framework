import os
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.exc import OperationalError

# Set isolated test settings with fake database URL before loading settings
os.environ["DATABASE_URL"] = (
    "postgresql://fake_user:fake_password@localhost:5432/fake_db?sslmode=require"
)

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {
        "message": "Agentic AI QA Framework API",
        "status": "running",
    }


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_db_health_success(client):
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_db.execute.return_value = mock_result

    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        response = client.get("/health/db")
        assert response.status_code == 200
        assert response.json() == {
            "status": "healthy",
            "database": "connected",
        }
    finally:
        app.dependency_overrides.clear()


def test_db_health_failure(client):
    mock_db = MagicMock()
    mock_db.execute.side_effect = OperationalError("connection refused", {}, None)

    app.dependency_overrides[get_db] = lambda: mock_db
    try:
        response = client.get("/health/db")
        assert response.status_code == 503
        assert response.json() == {
            "status": "unhealthy",
            "database": "unavailable",
        }
        assert "fake_password" not in response.text
        assert "connection refused" not in response.text
    finally:
        app.dependency_overrides.clear()

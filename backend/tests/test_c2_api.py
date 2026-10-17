"""Tests for C2 API endpoints, routing, error handling, and health compatibility."""

import os
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set isolated test settings with fake database URL before loading settings
os.environ["DATABASE_URL"] = (
    "postgresql://fake_user:fake_password@localhost:5432/fake_db?sslmode=require"
)

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.components.c2_state_aware_workflow.examples.refund_workflow import (  # noqa: E402
    get_draft_refund_create_request,
)
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client_with_sqlite_db():
    """Provides a TestClient with an isolated in-memory SQLite database dependency override."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


class TestC2Endpoints:
    """Tests the /api/v1/c2 REST endpoints."""

    def test_create_draft_model_api(self, client_with_sqlite_db: TestClient):
        request_obj = get_draft_refund_create_request()
        payload = request_obj.model_dump(mode="json")

        response = client_with_sqlite_db.post("/api/v1/c2/models", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["model_id"] == "ecommerce-refund-latest-paid"
        assert data["version"] == "1.0.0"
        assert data["lifecycle_status"] == "DRAFT"
        assert len(data["content_hash"]) == 64
        assert "definition" in data
        assert data["definition"]["initial_state"] == "S_START"

    def test_create_duplicate_model_returns_409(
        self, client_with_sqlite_db: TestClient
    ):
        request_obj = get_draft_refund_create_request()
        payload = request_obj.model_dump(mode="json")

        res1 = client_with_sqlite_db.post("/api/v1/c2/models", json=payload)
        assert res1.status_code == 201

        res2 = client_with_sqlite_db.post("/api/v1/c2/models", json=payload)
        assert res2.status_code == 409
        assert "already exists" in res2.json()["detail"]

    def test_create_model_invalid_payload_returns_422(
        self, client_with_sqlite_db: TestClient
    ):
        invalid_payload = {
            "project_id": "proj-1",
            "domain": "e-commerce",
            # missing name and definition
        }
        response = client_with_sqlite_db.post("/api/v1/c2/models", json=invalid_payload)
        assert response.status_code == 422

    def test_list_models_for_project_api(self, client_with_sqlite_db: TestClient):
        request_obj = get_draft_refund_create_request()
        client_with_sqlite_db.post(
            "/api/v1/c2/models", json=request_obj.model_dump(mode="json")
        )

        response = client_with_sqlite_db.get(
            "/api/v1/c2/models",
            params={"project_id": "nexacart-qa-synthetic"},
        )
        assert response.status_code == 200
        items = response.json()
        assert len(items) == 1
        assert items[0]["model_id"] == "ecommerce-refund-latest-paid"
        assert items[0]["lifecycle_status"] == "DRAFT"

    def test_get_model_version_api(self, client_with_sqlite_db: TestClient):
        request_obj = get_draft_refund_create_request()
        client_with_sqlite_db.post(
            "/api/v1/c2/models", json=request_obj.model_dump(mode="json")
        )

        response = client_with_sqlite_db.get(
            "/api/v1/c2/models/ecommerce-refund-latest-paid/versions/1.0.0"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["model_id"] == "ecommerce-refund-latest-paid"
        assert data["version"] == "1.0.0"

    def test_get_nonexistent_model_version_returns_404(
        self, client_with_sqlite_db: TestClient
    ):
        response = client_with_sqlite_db.get(
            "/api/v1/c2/models/nonexistent/versions/9.9.9"
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestHealthCompatibility:
    """Verifies that existing health routes remain 100% operational alongside C2."""

    def test_root_endpoint(self, client_with_sqlite_db: TestClient):
        response = client_with_sqlite_db.get("/")
        assert response.status_code == 200
        assert response.json()["status"] == "running"

    def test_health_endpoint(self, client_with_sqlite_db: TestClient):
        response = client_with_sqlite_db.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

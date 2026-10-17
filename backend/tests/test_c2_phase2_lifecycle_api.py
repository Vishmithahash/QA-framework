"""Tests for model lifecycle transitions, validation persistence, approval, and API routes."""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["DATABASE_URL"] = (
    "postgresql://fake_user:fake_password@localhost:5432/fake_db?sslmode=require"
)

from app.components.c2_state_aware_workflow.contracts.enums import (  # noqa: E402
    EvaluationVerdict,
    LifecycleStatus,
)
from app.components.c2_state_aware_workflow.examples.refund_workflow import (  # noqa: E402
    get_draft_refund_create_request,
    get_draft_refund_workflow_definition,
    get_draft_refund_workflow_input,
)
from app.components.c2_state_aware_workflow.schemas.api_models import (  # noqa: E402
    CreateDraftWorkflowModelRequest,
)
from app.components.c2_state_aware_workflow.services.model_service import (  # noqa: E402
    AmbiguousModelResolutionError,
    ApprovedModelImmutableError,
    ModelValidationFailedError,
    StaleValidationReportError,
    WorkflowModelService,
)
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def test_db_session():
    """Provides an isolated SQLite database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def api_client(test_db_session: Session):
    """Provides a TestClient wired to the isolated SQLite session."""

    def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


class TestProjectScopingAndDisambiguation:
    """Verifies that project scoping strictly prevents ambiguous retrieval and cross-project leakage."""

    def test_cross_project_identical_model_versions(self, test_db_session: Session):
        service = WorkflowModelService(test_db_session)
        definition = get_draft_refund_workflow_definition()

        # Project A
        req_a = CreateDraftWorkflowModelRequest(
            project_id="project-alpha",
            domain="e-commerce",
            name="Alpha Model",
            definition=definition.model_copy(update={"project_id": "project-alpha"}),
        )
        service.create_draft_model(req_a)

        # Project B with identical model_id and version
        req_b = CreateDraftWorkflowModelRequest(
            project_id="project-beta",
            domain="e-commerce",
            name="Beta Model",
            definition=definition.model_copy(update={"project_id": "project-beta"}),
        )
        service.create_draft_model(req_b)

        # Scoped retrieval for project-alpha
        rec_a = service.get_model_version(
            model_id=definition.model_id,
            version=definition.version,
            project_id="project-alpha",
        )
        assert rec_a.project_id == "project-alpha"
        assert rec_a.name == "Alpha Model"

        # Scoped retrieval for project-beta
        rec_b = service.get_model_version(
            model_id=definition.model_id,
            version=definition.version,
            project_id="project-beta",
        )
        assert rec_b.project_id == "project-beta"
        assert rec_b.name == "Beta Model"

        # Unscoped retrieval raises AmbiguousModelResolutionError
        with pytest.raises(
            AmbiguousModelResolutionError, match="Ambiguous model retrieval"
        ):
            service.get_model_version(
                model_id=definition.model_id,
                version=definition.version,
                project_id=None,
            )


class TestLifecycleTransitionsAndImmutability:
    """Verifies the progression DRAFT -> VALIDATED -> APPROVED and immutability guarantees."""

    def test_lifecycle_draft_to_validated_to_approved(self, test_db_session: Session):
        service = WorkflowModelService(test_db_session)
        request = get_draft_refund_create_request()

        # Step 1: Newly created model is strictly DRAFT
        record = service.create_draft_model(request)
        assert record.lifecycle_status == LifecycleStatus.DRAFT.value

        # Step 2: Validate model
        model_rec, val_rec, report = service.validate_model_version(
            project_id=record.project_id,
            model_id=record.model_id,
            version=record.version,
        )
        assert report.is_valid is True
        assert model_rec.lifecycle_status == LifecycleStatus.VALIDATED.value
        assert val_rec.definition_hash == model_rec.content_hash

        # Step 3: Approve model
        approved_rec = service.approve_model_version(
            project_id=record.project_id,
            model_id=record.model_id,
            version=record.version,
            reviewer="qa-lead@test.internal",
            review_basis="Tested against PRD refund requirements v2.1",
            review_notes="All guards and state effects conformed.",
            is_development_review=True,
        )
        assert approved_rec.lifecycle_status == LifecycleStatus.APPROVED.value
        assert approved_rec.reviewed_by is not None
        assert (
            approved_rec.review_basis == "Tested against PRD refund requirements v2.1"
        )
        assert approved_rec.approved_at is not None

        # Content hash unchanged after metadata and approval updates
        assert approved_rec.content_hash == record.content_hash

        # Step 4: Approved version cannot be mutated
        with pytest.raises(ApprovedModelImmutableError):
            service.assert_version_mutable(approved_rec)

    def test_approval_blocked_without_validation(self, test_db_session: Session):
        service = WorkflowModelService(test_db_session)
        request = get_draft_refund_create_request()
        record = service.create_draft_model(request)

        # Attempting approval directly on DRAFT without validation raises error
        with pytest.raises(
            ModelValidationFailedError,
            match="Validation is mandatory prior to approval",
        ):
            service.approve_model_version(
                project_id=record.project_id,
                model_id=record.model_id,
                version=record.version,
                reviewer="tester",
                review_basis="Premature approval",
            )

    def test_approval_blocked_on_stale_validation_hash(self, test_db_session: Session):
        service = WorkflowModelService(test_db_session)
        request = get_draft_refund_create_request()
        record = service.create_draft_model(request)

        # Validate
        service.validate_model_version(
            project_id=record.project_id,
            model_id=record.model_id,
            version=record.version,
        )

        # Simulate definition change in draft (e.g. hash modified)
        record.content_hash = (
            "stale_hash_1234567890abcdef1234567890abcdef1234567890abcdef12345678"
        )
        test_db_session.commit()

        # Approval fails because latest validation report definition hash does not match current hash
        with pytest.raises(
            StaleValidationReportError, match="Re-validation is required"
        ):
            service.approve_model_version(
                project_id=record.project_id,
                model_id=record.model_id,
                version=record.version,
                reviewer="tester",
                review_basis="Review with stale validation",
            )

    def test_create_new_draft_version_from_approved(self, test_db_session: Session):
        service = WorkflowModelService(test_db_session)
        request = get_draft_refund_create_request()
        record = service.create_draft_model(request)

        # Validate and approve version 1.0.0
        service.validate_model_version(
            record.project_id, record.model_id, record.version
        )
        service.approve_model_version(
            record.project_id, record.model_id, record.version, "reviewer", "basis"
        )

        # Create new version 1.1.0
        def_obj = get_draft_refund_workflow_definition()
        new_def = def_obj.model_copy(update={"version": "1.1.0"})
        new_ver = service.create_new_draft_version(
            project_id=record.project_id,
            model_id=record.model_id,
            new_version="1.1.0",
            definition=new_def,
        )
        assert new_ver.version == "1.1.0"
        assert new_ver.lifecycle_status == LifecycleStatus.DRAFT.value

    def test_model_readiness_verdicts(self, test_db_session: Session):
        service = WorkflowModelService(test_db_session)
        request = get_draft_refund_create_request()
        record = service.create_draft_model(request)

        # Draft model readiness check -> MODEL NOT READY
        r_draft = service.check_model_readiness(
            record.project_id, record.model_id, record.version
        )
        assert not r_draft.is_ready
        assert r_draft.status == "MODEL_NOT_READY"
        assert r_draft.verdict == EvaluationVerdict.MODEL_NOT_READY

        # Validate and approve
        service.validate_model_version(
            record.project_id, record.model_id, record.version
        )
        service.approve_model_version(
            record.project_id, record.model_id, record.version, "lead", "basis"
        )

        # Approved model readiness check -> READY (verdict is None, NEVER runtime PASS)
        r_ready = service.check_model_readiness(
            record.project_id, record.model_id, record.version
        )
        assert r_ready.is_ready is True
        assert r_ready.status == "READY"
        assert r_ready.verdict is None


class TestPhase2APIRoutes:
    """Verifies all Phase 2 REST API endpoints."""

    def test_propose_model_api(self, api_client: TestClient):
        wf_input = get_draft_refund_workflow_input()
        payload = {
            "workflow_input": wf_input.model_dump(mode="json"),
            "model_id": "api-proposed-refund",
            "version": "1.0.0",
        }
        res = api_client.post("/api/v1/c2/models/propose", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["candidate_model"]["model_id"] == "api-proposed-refund"
        assert data["builder_provenance"] == "deterministic_model_builder_v2"

    def test_propose_model_insufficient_input_returns_422(self, api_client: TestClient):
        wf_input = get_draft_refund_workflow_input()
        input_dict = wf_input.model_dump(mode="json")
        input_dict["workflow_rules"] = []  # Empty!

        payload = {"workflow_input": input_dict}
        res = api_client.post("/api/v1/c2/models/propose", json=payload)
        assert res.status_code == 422
        assert "insufficient input" in res.json()["detail"]["message"].lower()

    def test_validate_and_get_validation_report_api(self, api_client: TestClient):
        # 1. Create model
        create_req = get_draft_refund_create_request().model_dump(mode="json")
        res_create = api_client.post("/api/v1/c2/models", json=create_req)
        assert res_create.status_code == 201

        # 2. Validate
        val_payload = {"project_id": "nexacart-qa-synthetic"}
        res_val = api_client.post(
            "/api/v1/c2/models/ecommerce-refund-latest-paid/versions/1.0.0/validate",
            json=val_payload,
        )
        assert res_val.status_code == 200
        val_data = res_val.json()
        assert val_data["is_valid"] is True
        assert val_data["has_blocking_issues"] is False
        assert "check_graph_reachability" in val_data["checks_performed"]

        # 3. Retrieve validation report
        res_get = api_client.get(
            "/api/v1/c2/models/ecommerce-refund-latest-paid/versions/1.0.0/validation",
            params={"project_id": "nexacart-qa-synthetic"},
        )
        assert res_get.status_code == 200
        assert res_get.json()["definition_hash"] == val_data["definition_hash"]

    def test_approve_model_api(self, api_client: TestClient):
        # Create and validate
        create_req = get_draft_refund_create_request().model_dump(mode="json")
        api_client.post("/api/v1/c2/models", json=create_req)
        api_client.post(
            "/api/v1/c2/models/ecommerce-refund-latest-paid/versions/1.0.0/validate",
            json={"project_id": "nexacart-qa-synthetic"},
        )

        # Approve
        approve_payload = {
            "project_id": "nexacart-qa-synthetic",
            "reviewer": "alice@qa.internal",
            "review_basis": "Manual rule inspection against e-commerce PRD",
            "review_notes": "All checks validated cleanly.",
            "is_development_review": True,
        }
        res_app = api_client.post(
            "/api/v1/c2/models/ecommerce-refund-latest-paid/versions/1.0.0/approve",
            json=approve_payload,
        )
        assert res_app.status_code == 200
        data = res_app.json()
        assert data["lifecycle_status"] == "APPROVED"
        assert "[DEV_REVIEW]" in data["reviewed_by"]
        assert data["approved_at"] is not None

    def test_create_new_version_api(self, api_client: TestClient):
        # Create draft model
        create_req = get_draft_refund_create_request().model_dump(mode="json")
        api_client.post("/api/v1/c2/models", json=create_req)

        # Create new version 2.0.0
        def_obj = get_draft_refund_workflow_definition()
        new_def_dict = def_obj.model_dump(mode="json")
        new_def_dict["version"] = "2.0.0"

        payload = {
            "project_id": "nexacart-qa-synthetic",
            "version": "2.0.0",
            "definition": new_def_dict,
        }
        res_ver = api_client.post(
            "/api/v1/c2/models/ecommerce-refund-latest-paid/versions",
            json=payload,
        )
        assert res_ver.status_code == 201
        data = res_ver.json()
        assert data["version"] == "2.0.0"
        assert data["lifecycle_status"] == "DRAFT"

    def test_readiness_endpoint_api(self, api_client: TestClient):
        create_req = get_draft_refund_create_request().model_dump(mode="json")
        api_client.post("/api/v1/c2/models", json=create_req)

        # Unapproved model -> MODEL NOT READY
        res_unreadiness = api_client.get(
            "/api/v1/c2/models/ecommerce-refund-latest-paid/versions/1.0.0/readiness",
            params={"project_id": "nexacart-qa-synthetic"},
        )
        assert res_unreadiness.status_code == 200
        assert res_unreadiness.json()["is_ready"] is False
        assert res_unreadiness.json()["status"] == "MODEL_NOT_READY"

        # Validate and approve
        api_client.post(
            "/api/v1/c2/models/ecommerce-refund-latest-paid/versions/1.0.0/validate",
            json={"project_id": "nexacart-qa-synthetic"},
        )
        api_client.post(
            "/api/v1/c2/models/ecommerce-refund-latest-paid/versions/1.0.0/approve",
            json={
                "project_id": "nexacart-qa-synthetic",
                "reviewer": "approver",
                "review_basis": "verified",
            },
        )

        # Approved model -> READY
        res_ready = api_client.get(
            "/api/v1/c2/models/ecommerce-refund-latest-paid/versions/1.0.0/readiness",
            params={"project_id": "nexacart-qa-synthetic"},
        )
        assert res_ready.status_code == 200
        assert res_ready.json()["is_ready"] is True
        assert res_ready.json()["status"] == "READY"
        assert res_ready.json()["verdict"] is None

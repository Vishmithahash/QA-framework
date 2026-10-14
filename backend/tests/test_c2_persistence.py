"""Tests for C2 workflow model persistence, canonical hashing, and lifecycle immutability."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.components.c2_state_aware_workflow.contracts.enums import LifecycleStatus
from app.components.c2_state_aware_workflow.examples.refund_workflow import (
    get_draft_refund_create_request,
    get_draft_refund_workflow_definition,
)
from app.components.c2_state_aware_workflow.services.model_service import (
    ApprovedModelImmutableError,
    ModelNotFoundError,
    ModelVersionAlreadyExistsError,
    WorkflowModelService,
    compute_canonical_content_hash,
)
from app.database import Base


@pytest.fixture
def isolated_db_session():
    """Provides an isolated in-memory SQLite database session for unit tests."""
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


class TestModelPersistenceAndHashing:
    """Verifies database persistence, canonical hashing, and retrieval."""

    def test_deterministic_content_hashing(self):
        definition = get_draft_refund_workflow_definition()
        hash1 = compute_canonical_content_hash(definition)
        hash2 = compute_canonical_content_hash(definition)
        assert hash1 == hash2
        assert len(hash1) == 64

    def test_create_draft_model_success(self, isolated_db_session: Session):
        service = WorkflowModelService(isolated_db_session)
        request = get_draft_refund_create_request()

        record = service.create_draft_model(request)

        assert record.id is not None
        assert record.model_id == "ecommerce-refund-latest-paid"
        assert record.version == "1.0.0"
        assert record.project_id == "nexacart-qa-synthetic"
        assert record.lifecycle_status == LifecycleStatus.DRAFT.value
        assert record.content_hash == compute_canonical_content_hash(request.definition)
        assert record.created_at is not None

    def test_duplicate_version_raises_conflict(self, isolated_db_session: Session):
        service = WorkflowModelService(isolated_db_session)
        request = get_draft_refund_create_request()

        service.create_draft_model(request)

        with pytest.raises(ModelVersionAlreadyExistsError):
            service.create_draft_model(request)

    def test_list_models_for_project(self, isolated_db_session: Session):
        service = WorkflowModelService(isolated_db_session)
        request = get_draft_refund_create_request()
        service.create_draft_model(request)

        models = service.list_models_for_project("nexacart-qa-synthetic")
        assert len(models) == 1
        assert models[0].model_id == "ecommerce-refund-latest-paid"

        empty_list = service.list_models_for_project("nonexistent-project")
        assert len(empty_list) == 0

    def test_get_model_version(self, isolated_db_session: Session):
        service = WorkflowModelService(isolated_db_session)
        request = get_draft_refund_create_request()
        service.create_draft_model(request)

        retrieved = service.get_model_version(
            model_id="ecommerce-refund-latest-paid",
            version="1.0.0",
        )
        assert retrieved.name == request.name
        assert retrieved.definition["initial_state"] == "S_START"

    def test_get_nonexistent_model_raises_not_found(self, isolated_db_session: Session):
        service = WorkflowModelService(isolated_db_session)
        with pytest.raises(ModelNotFoundError):
            service.get_model_version("unknown-model", "1.0.0")

    def test_approved_version_immutability(self, isolated_db_session: Session):
        service = WorkflowModelService(isolated_db_session)
        request = get_draft_refund_create_request()
        record = service.create_draft_model(request)

        # Mutate to APPROVED to simulate a future approval
        record.lifecycle_status = LifecycleStatus.APPROVED.value
        isolated_db_session.commit()

        # Enforce immutability
        with pytest.raises(ApprovedModelImmutableError):
            service.assert_version_mutable(record)

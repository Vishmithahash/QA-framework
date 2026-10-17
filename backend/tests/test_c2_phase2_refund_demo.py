"""Tests for the complete Phase 2 refund reference model and lifecycle demonstration."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.components.c2_state_aware_workflow.examples.refund_workflow import (
    demonstrate_refund_lifecycle,
    get_draft_refund_workflow_definition,
    get_draft_refund_workflow_input,
)
from app.components.c2_state_aware_workflow.services.model_validator import (
    WorkflowModelValidator,
)
from app.database import Base


@pytest.fixture
def isolated_db():
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


class TestRefundModelDemonstration:
    """Demonstrates complete lifecycle of the synthetic 'Refund my latest paid order' model."""

    def test_full_lifecycle_demonstration(self, isolated_db: Session):
        demo_result = demonstrate_refund_lifecycle(isolated_db)

        assert demo_result["candidate_model_id"] == "ecommerce-refund-latest-paid"
        assert demo_result["lifecycle_status"] == "APPROVED"
        assert demo_result["is_ready"] is True
        assert "[DEV_REVIEW]" in demo_result["reviewed_by"]
        assert len(demo_result["content_hash"]) == 64
        assert "check_graph_reachability" in demo_result["checks_performed"]
        assert "check_rejection_path_protected_state" in demo_result["checks_performed"]

    def test_refund_definition_validation(self):
        validator = WorkflowModelValidator()
        model = get_draft_refund_workflow_definition()
        report = validator.validate(model)

        assert report.is_valid is True
        assert report.has_blocking_issues is False
        assert len(report.errors) == 0

        # Permitted alternative path warning is present and non-blocking
        assert any(
            w.issue_code == "PERMITTED_ALTERNATIVE_PATH" for w in report.warnings
        )
        assert any(
            a.issue_code == "ASSUMPTION_SYNTHETIC_MODEL"
            for a in report.unresolved_assumptions
        )

    def test_fixture_entity_alignment(self):
        wf_input = get_draft_refund_workflow_input()
        fixture = wf_input.fixture_references[0]

        # Customer 42
        assert fixture.initial_entities["customer"]["id"] == 42

        # Orders: 501 (paid, older), 503 (paid, latest), 502 (unpaid)
        orders = {o["id"]: o for o in fixture.initial_entities["orders"]}
        assert orders[501]["payment_status"] == "PAID"
        assert orders[503]["payment_status"] == "PAID"
        assert orders[502]["payment_status"] == "UNPAID"

        # Chronological ordering: 503 > 501
        assert orders[503]["created_at"] > orders[501]["created_at"]

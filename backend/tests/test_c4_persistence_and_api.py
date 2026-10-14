"""Integration tests for C4 persistence layer and FastAPI endpoints using isolated test storage."""

from collections.abc import Generator
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from app.components.c4_policy_aware_safety.contracts.artifacts import (
    ArtifactKind,
    ArtifactVersion,
)
from app.components.c4_policy_aware_safety.contracts.findings import (
    EvaluationFinding,
    PolicyVerdict,
    ReasonCode,
    Severity,
    ViolationStage,
)
from app.components.c4_policy_aware_safety.contracts.policy import (
    ActionSelector,
    ContractLifecycleStatus,
    EvaluationBoundary,
    PolicyContract,
    PolicyFamily,
    PolicyRequirement,
    PolicyRule,
    PrincipalSelector,
    ResourceSelector,
)
from app.components.c4_policy_aware_safety.contracts.sources import SourceReference
from app.components.c4_policy_aware_safety.persistence.models import (
    Base,
)
from app.components.c4_policy_aware_safety.persistence.repository import C4Repository
from app.database import get_db
from app.main import app

# Isolated in-memory SQLite engine for tests
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_repository_artifact_and_contract_crud(db_session: Session):
    """Test saving and retrieving artifacts and contracts via C4Repository."""
    repo = C4Repository(db_session)

    # 1. Save artifact
    art = ArtifactVersion(
        project_id="proj-test",
        artifact_id="art-test-1",
        version="1.0.0",
        kind=ArtifactKind.POLICY_DOCUMENT,
        content_hash="abc123hash",
        normalized_content="Role SUPPORT must not refund orders.",
    )
    repo.save_artifact(art)

    retrieved_art = repo.get_artifact("proj-test", "art-test-1", "1.0.0")
    assert retrieved_art is not None
    assert retrieved_art.artifact_id == "art-test-1"

    # Cross-project isolation check
    assert repo.get_artifact("other-proj", "art-test-1", "1.0.0") is None

    # 2. Save contract
    rule = PolicyRule(
        rule_id="r1",
        family=PolicyFamily.AUTHORIZATION,
        principal_selector=PrincipalSelector(role="SUPPORT"),
        action_selector=ActionSelector(action="refund"),
        resource_selector=ResourceSelector(resource_type="orders"),
        requirement=PolicyRequirement.DENY,
        evaluation_boundary=EvaluationBoundary.ATTEMPTED_ACTION,
        sources=[
            SourceReference(
                artifact_id="art-test-1",
                artifact_version="1.0.0",
                supporting_excerpt="Role SUPPORT must not refund orders.",
            )
        ],
    )
    contract = PolicyContract(
        contract_id="c1",
        project_id="proj-test",
        version=1,
        lifecycle_status=ContractLifecycleStatus.DRAFT,
        rules=[rule],
    )
    contract.content_hash = contract.compute_content_hash()
    repo.save_contract(contract)

    retrieved_contract = repo.get_contract("proj-test", "c1", 1)
    assert retrieved_contract is not None
    assert retrieved_contract.contract_id == "c1"
    assert len(retrieved_contract.rules) == 1
    assert retrieved_contract.rules[0].rule_id == "r1"

    # 3. Save finding
    finding = EvaluationFinding(
        finding_id="f1",
        project_id="proj-test",
        contract_id="c1",
        contract_version=1,
        rule_id="r1",
        rule_version=1,
        verdict=PolicyVerdict.FAIL,
        reason_codes=[ReasonCode.PROHIBITED_ACTION_ATTEMPTED],
        severity=Severity.HIGH,
        source_policy_reference=rule.sources[0],
        violation_stage=ViolationStage.ATTEMPTED_PROHIBITED_ACTION,
        explanation="Attempted prohibited action",
    )
    repo.save_findings([finding])

    findings = repo.get_findings("proj-test")
    assert len(findings) == 1
    assert findings[0].finding_id == "f1"
    assert findings[0].verdict == PolicyVerdict.FAIL


def test_api_full_c4_workflow(client: TestClient):
    """
    Test full end-to-end API lifecycle:
    1. Register text artifact
    2. Derive candidate rules
    3. Create contract
    4. Validate contract
    5. Attempt premature evaluation -> HTTP 400
    6. Explicitly accept contract
    7. Evaluate against evidence -> 200 with C4EvaluationReport
    8. Query findings
    """
    proj_id = "proj-e2e"

    # 1. Register text artifact
    artifact_payload = {
        "artifact_id": "policy-sec-1",
        "version": "1.0.0",
        "kind": "POLICY_DOCUMENT",
        "content": "Role CUSTOMER_SUPPORT requires approval from MANAGER to issue_refund orders where amount > 5000.",
    }
    art_resp = client.post(
        f"/api/v1/projects/{proj_id}/c4/artifacts/text", json=artifact_payload
    )
    assert art_resp.status_code == 201
    art_data = art_resp.json()
    assert art_data["artifact_id"] == "policy-sec-1"

    # 2. Derive candidate rules via controlled language
    derive_payload = {
        "artifact_id": "policy-sec-1",
        "artifact_version": "1.0.0",
        "extraction_method": "controlled_language",
    }
    derive_resp = client.post(
        f"/api/v1/projects/{proj_id}/c4/derive-candidate-rules", json=derive_payload
    )
    assert derive_resp.status_code == 200
    derive_data = derive_resp.json()
    rules = derive_data["candidate_rules"]
    assert len(rules) == 1

    # 3. Create contract draft
    contract_payload = {
        "contract_id": "contract-refund-controls",
        "version": 1,
        "rules": rules,
        "referenced_artifact_versions": {"policy-sec-1": "1.0.0"},
    }
    create_resp = client.post(
        f"/api/v1/projects/{proj_id}/c4/contracts", json=contract_payload
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["lifecycle_status"] == "DRAFT"

    # 4. Validate contract
    val_resp = client.post(
        f"/api/v1/projects/{proj_id}/c4/contracts/contract-refund-controls/versions/1/validate"
    )
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["lifecycle_status"] == "VALIDATED"
    assert len(val_data["validation_issues"]) == 0

    # 5. Premature evaluation attempt before acceptance must return 400 Bad Request
    eval_payload = {
        "evidence": {
            "project_id": proj_id,
            "origin": "SYNTHETIC_DEVELOPER_FIXTURE",
            "principal": {"principal_id": "u1", "role": "CUSTOMER_SUPPORT"},
            "action_attempts": [
                {
                    "action_id": "act-1",
                    "tool_name": "issue_refund",
                    "arguments": {"amount": 7500},
                }
            ],
            "approvals": [],
        }
    }
    premature_eval = client.post(
        f"/api/v1/projects/{proj_id}/c4/contracts/contract-refund-controls/versions/1/evaluate",
        json=eval_payload,
    )
    assert premature_eval.status_code == 400
    assert "Only ACCEPTED contracts can be evaluated" in premature_eval.json()["detail"]

    # 6. Explicitly accept contract
    accept_payload = {
        "accepted_by": "LEAD_REVIEWER",
        "justification": "Approved per security compliance sign-off",
    }
    accept_resp = client.post(
        f"/api/v1/projects/{proj_id}/c4/contracts/contract-refund-controls/versions/1/accept",
        json=accept_payload,
    )
    assert accept_resp.status_code == 200
    assert accept_resp.json()["lifecycle_status"] == "ACCEPTED"

    # 7. Evaluate accepted contract against evidence
    eval_resp = client.post(
        f"/api/v1/projects/{proj_id}/c4/contracts/contract-refund-controls/versions/1/evaluate",
        json=eval_payload,
    )
    assert eval_resp.status_code == 200
    report_data = eval_resp.json()
    assert report_data["aggregate_verdict"] == "FAIL"
    assert len(report_data["findings"]) == 1
    assert (
        report_data["findings"][0]["violation_stage"] == "ATTEMPTED_PROHIBITED_ACTION"
    )

    # 8. Query stored findings
    findings_resp = client.get(f"/api/v1/projects/{proj_id}/c4/findings")
    assert findings_resp.status_code == 200
    findings_data = findings_resp.json()
    assert len(findings_data) == 1
    assert findings_data[0]["verdict"] == "FAIL"

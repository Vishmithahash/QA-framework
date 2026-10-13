"""
Hermetic automated tests for Component 3 (C3) Phase 1 foundation:
- Operational Fault Catalogue (5 families, no active injector).
- Versioned Pydantic contracts and Draft 2020-12 JSON Schema generation.
- Deterministic static validator (STATIC_VALID vs TEST_NOT_READY).
- Capability combinations (no cross-product assumptions).
- Read-only vs side-effecting rules, AFTER_COMMIT commit evidence, PARTIAL_EFFECT constraints.
- Recovery budget counting semantics and coherence.
- Sanitized 422 responses without echoing secrets or raw inputs.
- No database or network calls during C3 operations.
- Application OpenAPI registration and preservation of existing health routes.
"""

import json
import os
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import pytest

# Ensure isolated hermetic test environment before loading settings
os.environ["DATABASE_URL"] = (
    "postgresql://fake_user:fake_password@localhost:5432/fake_db?sslmode=require"
)

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.components.c3_robustness_recovery.schemas import (  # noqa: E402
    AdapterCapability,
    AdapterCapabilityManifest,
    AssertionMetadata,
    CandidateFaultCase,
    CaseValidationRequest,
    CaseValidationResponse,
    EffectPhase,
    EnvironmentMetadata,
    FaultCatalogResponse,
    FaultFamily,
    FixtureMetadata,
    HookType,
    ObservationMethodMetadata,
    RecoveryContract,
    ReleaseRule,
    ReleaseRuleMode,
    ServerError5xxPayload,
    TaskMetadata,
    TerminalOutcome,
    TimeoutMode,
    TimeoutPayload,
    ToolDeclaration,
    TriggerDefinition,
    ValidationScope,
    ValidationStatus,
)
from app.components.c3_robustness_recovery.validation import (  # noqa: E402
    get_operational_fault_catalog,
    validate_candidate_case,
)
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Test Fixtures & Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def build_valid_test_request() -> CaseValidationRequest:
    """Helper to construct a fully consistent, statically valid test request."""
    case = CandidateFaultCase(
        schema_version="1.0.0",
        project_id="proj-ecom-01",
        case_id="case-payment-timeout-01",
        case_family="CF-PAYMENT-TIMEOUT",
        domain="e-commerce",
        task_id="task-checkout-01",
        task_version="1.0.0",
        tool_id="charge_payment",
        tool_version="1.0.0",
        fixture_id="fix-cart-empty",
        fixture_version="1.0.0",
        adapter_id="adapter-mock-gateway",
        adapter_version="1.0.0",
        recovery_contract_id="rec-contract-standard",
        recovery_contract_version="1.0.0",
        trigger=TriggerDefinition(
            tool_id="charge_payment",
            call_occurrence=1,
            hook=HookType.DURING_TRANSPORT,
        ),
        fault_family=FaultFamily.TIMEOUT_OR_DISCONNECTION,
        effect_phase=EffectPhase.BEFORE_EFFECT,
        payload=TimeoutPayload(
            family=FaultFamily.TIMEOUT_OR_DISCONNECTION,
            mode=TimeoutMode.CONNECTION_TIMEOUT,
            delay_ms=5000,
        ),
        release_rule=ReleaseRule(
            mode=ReleaseRuleMode.SINGLE_CALL,
            max_fault_occurrences=1,
        ),
        required_assertion_ids=["assert_order_not_duplicated", "assert_user_notified"],
        seed=42,
    )

    manifest = AdapterCapabilityManifest(
        schema_version="1.0.0",
        adapter_id="adapter-mock-gateway",
        adapter_version="1.0.0",
        tools=[
            ToolDeclaration(
                tool_id="charge_payment",
                tool_version="1.0.0",
                is_side_effecting=True,
            ),
            ToolDeclaration(
                tool_id="search_products",
                tool_version="1.0.0",
                is_side_effecting=False,
            ),
        ],
        capabilities=[
            AdapterCapability(
                fault_family=FaultFamily.TIMEOUT_OR_DISCONNECTION,
                effect_phase=EffectPhase.BEFORE_EFFECT,
                hook=HookType.DURING_TRANSPORT,
                observation_method="obs_network_trace",
                allowed_modes=["CONNECTION_TIMEOUT", "READ_TIMEOUT"],
                min_delay_ms=100,
                max_delay_ms=10000,
                supported_release_modes=[
                    ReleaseRuleMode.SINGLE_CALL,
                    ReleaseRuleMode.COUNT_BASED,
                ],
                is_application_aware=False,
            ),
            AdapterCapability(
                fault_family=FaultFamily.TRANSIENT_5XX_SERVER_ERROR,
                effect_phase=EffectPhase.AFTER_COMMIT,
                hook=HookType.POST_COMMIT,
                observation_method="obs_db_commit_log",
                allowed_status_codes=[500, 502, 503],
                supported_release_modes=[ReleaseRuleMode.SINGLE_CALL],
                is_application_aware=True,
            ),
        ],
    )

    contract = RecoveryContract(
        contract_id="rec-contract-standard",
        version="1.0.0",
        permitted_terminal_outcomes=[
            TerminalOutcome.SUCCESS,
            TerminalOutcome.GRACEFUL_DEGRADATION,
            TerminalOutcome.SAFE_ABORT,
        ],
        graceful_stopping_conditions=["max_retries_reached", "circuit_breaker_tripped"],
        max_total_attempts=3,
        max_retries=2,
        timeout_budget_seconds=30.0,
        required_assertion_ids=["assert_order_not_duplicated"],
        allow_duplicate_side_effects=False,
        truthful_completion_required=True,
        forbid_unsafe_retries=True,
        rule_ids=["REC-01-NO-DUPLICATE", "REC-02-BOUNDED-RETRY"],
    )

    env = EnvironmentMetadata(
        task=TaskMetadata(
            task_id="task-checkout-01",
            task_version="1.0.0",
            domain="e-commerce",
        ),
        fixture=FixtureMetadata(
            fixture_id="fix-cart-empty",
            fixture_version="1.0.0",
            supports_reset=True,
            supports_observation=True,
            has_commit_observation=True,
        ),
        available_assertions=[
            AssertionMetadata(
                assertion_id="assert_order_not_duplicated",
                assertion_type="STATE_INVARIANT",
                description="Verifies no duplicate charge was placed in database",
            ),
            AssertionMetadata(
                assertion_id="assert_user_notified",
                assertion_type="AGENT_OUTPUT",
                description="Verifies user was informed about connection problem",
            ),
        ],
        observation_methods=[
            ObservationMethodMetadata(
                method_id="obs_network_trace",
                description="Captures gateway packet level delays and disconnects",
            ),
            ObservationMethodMetadata(
                method_id="obs_db_commit_log",
                description="Direct inspection of Postgres commit logs and idempotency keys",
            ),
        ],
    )

    return CaseValidationRequest(
        case=case,
        adapter_manifest=manifest,
        recovery_contract=contract,
        environment_metadata=env,
    )


# ---------------------------------------------------------------------------
# 1. Operational Fault Catalogue Tests
# ---------------------------------------------------------------------------


def test_fault_catalog_contains_exactly_five_families():
    """Verify catalogue contains exactly the five operational families and no active injector."""
    catalog = get_operational_fault_catalog()
    assert isinstance(catalog, FaultCatalogResponse)
    assert catalog.injection_implemented is False

    expected_families = {
        FaultFamily.TIMEOUT_OR_DISCONNECTION,
        FaultFamily.TRANSIENT_5XX_SERVER_ERROR,
        FaultFamily.HTTP_429_RATE_LIMITING,
        FaultFamily.TOOL_UNAVAILABILITY,
        FaultFamily.MALFORMED_OR_TRUNCATED_RESPONSE,
    }

    actual_families = {f.family for f in catalog.families}
    assert actual_families == expected_families
    assert len(catalog.families) == 5

    for f in catalog.families:
        assert f.injection_status == "NOT_IMPLEMENTED"


def test_fault_catalog_api_endpoint(client):
    """GET /api/v1/c3/fault-catalog returns HTTP 200 with explicit 5 families."""
    response = client.get("/api/v1/c3/fault-catalog")
    assert response.status_code == 200
    data = response.json()
    assert data["injection_implemented"] is False
    assert len(data["families"]) == 5
    family_names = [f["family"] for f in data["families"]]
    assert "TIMEOUT_OR_DISCONNECTION" in family_names
    assert "TRANSIENT_5XX_SERVER_ERROR" in family_names
    assert "HTTP_429_RATE_LIMITING" in family_names
    assert "TOOL_UNAVAILABILITY" in family_names
    assert "MALFORMED_OR_TRUNCATED_RESPONSE" in family_names


# ---------------------------------------------------------------------------
# 2. Static Validation: Consistent Case
# ---------------------------------------------------------------------------


def test_consistent_case_returns_static_valid(client):
    """A consistent case returns STATIC_VALID, execution_ready=false, pending checks, recovery_verdict=null."""
    req = build_valid_test_request()
    payload = json.loads(req.model_dump_json())

    response = client.post("/api/v1/c3/cases/validate", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["validation_scope"] == ValidationScope.STATIC_ONLY.value
    assert data["validation_status"] == ValidationStatus.STATIC_VALID.value
    assert data["execution_ready"] is False
    assert data["recovery_verdict"] is None
    assert data["reasons"] == []

    expected_pending = [
        "actual_fixture_reset",
        "trigger_reachability",
        "observation_access",
        "injection_effect_phase_fidelity_verification",
    ]
    for check in expected_pending:
        assert check in data["pending_checks"]


# ---------------------------------------------------------------------------
# 3. Cross-Product Combination & Undeclared Capabilities
# ---------------------------------------------------------------------------


def test_unsupported_cross_product_combination_not_inferred():
    """
    Manifest declares:
    - (TIMEOUT, BEFORE_EFFECT, DURING_TRANSPORT)
    - (TRANSIENT_5XX, AFTER_COMMIT, POST_COMMIT)
    Case requests (TIMEOUT, AFTER_COMMIT, POST_COMMIT).
    Validator must NOT infer combination and must return TEST_NOT_READY.
    """
    req = build_valid_test_request()
    # Modify case to mix timeout with AFTER_COMMIT and POST_COMMIT
    # Even though both exist in manifest under different families, this specific combination is not declared
    req_dict = json.loads(req.model_dump_json())
    req_dict["case"]["effect_phase"] = "AFTER_COMMIT"
    req_dict["case"]["trigger"]["hook"] = "POST_COMMIT"

    # Re-validate model
    mutated_req = CaseValidationRequest.model_validate(req_dict)
    resp = validate_candidate_case(mutated_req)

    assert resp.validation_status == ValidationStatus.TEST_NOT_READY
    assert resp.execution_ready is False
    assert resp.recovery_verdict is None
    assert any(r.code == "CAPABILITY_COMBINATION_NOT_DECLARED" for r in resp.reasons)


# ---------------------------------------------------------------------------
# 4. Unknown Tool & Reference Consistency Checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_to_corrupt,corrupted_value,expected_reason_code",
    [
        ("tool_id", "unregistered_tool", "TOOL_NOT_IN_MANIFEST"),
        ("adapter_id", "wrong-adapter-id", "ADAPTER_REFERENCE_MISMATCH"),
        ("adapter_version", "9.9.9", "ADAPTER_VERSION_MISMATCH"),
        (
            "recovery_contract_id",
            "wrong-contract-id",
            "RECOVERY_CONTRACT_REFERENCE_MISMATCH",
        ),
        ("recovery_contract_version", "9.9.9", "RECOVERY_CONTRACT_VERSION_MISMATCH"),
        ("task_id", "wrong-task-id", "TASK_REFERENCE_MISMATCH"),
        ("task_version", "9.9.9", "TASK_VERSION_MISMATCH"),
        ("fixture_id", "wrong-fixture-id", "FIXTURE_REFERENCE_MISMATCH"),
        ("fixture_version", "9.9.9", "FIXTURE_VERSION_MISMATCH"),
    ],
)
def test_reference_and_tool_inconsistencies(
    field_to_corrupt, corrupted_value, expected_reason_code
):
    req = build_valid_test_request()
    req_dict = json.loads(req.model_dump_json())
    req_dict["case"][field_to_corrupt] = corrupted_value
    if field_to_corrupt == "tool_id":
        req_dict["case"]["trigger"]["tool_id"] = corrupted_value

    mutated_req = CaseValidationRequest.model_validate(req_dict)
    resp = validate_candidate_case(mutated_req)

    assert resp.validation_status == ValidationStatus.TEST_NOT_READY
    assert any(r.code == expected_reason_code for r in resp.reasons)


# ---------------------------------------------------------------------------
# 5. Read-Only vs Side-Effecting Rules & Effect Phases
# ---------------------------------------------------------------------------


def test_read_only_tool_cannot_declare_after_commit_or_partial_effect():
    """Read-only tools cannot declare AFTER_COMMIT or PARTIAL_EFFECT."""
    req = build_valid_test_request()
    req_dict = json.loads(req.model_dump_json())

    # Switch target tool to search_products (declared is_side_effecting=False)
    req_dict["case"]["tool_id"] = "search_products"
    req_dict["case"]["trigger"]["tool_id"] = "search_products"
    req_dict["case"]["effect_phase"] = "AFTER_COMMIT"
    req_dict["case"]["trigger"]["hook"] = "POST_COMMIT"

    mutated_req = CaseValidationRequest.model_validate(req_dict)
    resp = validate_candidate_case(mutated_req)

    assert resp.validation_status == ValidationStatus.TEST_NOT_READY
    assert any(
        r.code == "READ_ONLY_TOOL_EFFECT_PHASE_INCOMPATIBLE" for r in resp.reasons
    )


def test_timeout_cannot_assume_partial_effect():
    """PARTIAL_EFFECT must never be assumed from a timeout."""
    req = build_valid_test_request()
    req_dict = json.loads(req.model_dump_json())
    req_dict["case"]["effect_phase"] = "PARTIAL_EFFECT"

    mutated_req = CaseValidationRequest.model_validate(req_dict)
    resp = validate_candidate_case(mutated_req)

    assert resp.validation_status == ValidationStatus.TEST_NOT_READY
    assert any(r.code == "TIMEOUT_CANNOT_ASSUME_PARTIAL_EFFECT" for r in resp.reasons)


def test_after_commit_requires_application_aware_hook_and_commit_observation():
    """AFTER_COMMIT requires application-aware hook and independent commit observation."""
    # Case with AFTER_COMMIT and 5xx
    req = build_valid_test_request()
    req_dict = json.loads(req.model_dump_json())
    req_dict["case"]["fault_family"] = "TRANSIENT_5XX_SERVER_ERROR"
    req_dict["case"]["effect_phase"] = "AFTER_COMMIT"
    req_dict["case"]["trigger"]["hook"] = "POST_COMMIT"
    req_dict["case"]["payload"] = json.loads(
        ServerError5xxPayload(
            family=FaultFamily.TRANSIENT_5XX_SERVER_ERROR,
            status_code=500,
            error_message="Commit Succeeded but Response Lost",
        ).model_dump_json()
    )
    # Turn off fixture commit observation
    req_dict["environment_metadata"]["fixture"]["has_commit_observation"] = False

    mutated_req = CaseValidationRequest.model_validate(req_dict)
    resp = validate_candidate_case(mutated_req)

    assert resp.validation_status == ValidationStatus.TEST_NOT_READY
    assert any(
        r.code == "AFTER_COMMIT_MISSING_COMMIT_OBSERVATION" for r in resp.reasons
    )


# ---------------------------------------------------------------------------
# 6. Missing Assertions and Fixture Support Checks
# ---------------------------------------------------------------------------


def test_missing_assertion_references():
    """Required assertions in case or contract must be declared in environment metadata."""
    req = build_valid_test_request()
    req_dict = json.loads(req.model_dump_json())
    req_dict["case"]["required_assertion_ids"].append("assert_unregistered_ghost_id")

    mutated_req = CaseValidationRequest.model_validate(req_dict)
    resp = validate_candidate_case(mutated_req)

    assert resp.validation_status == ValidationStatus.TEST_NOT_READY
    assert any(r.code == "CASE_ASSERTION_NOT_FOUND" for r in resp.reasons)


def test_fixture_reset_and_observation_unsupported():
    """Fixture metadata must declare supports_reset=True and supports_observation=True."""
    req = build_valid_test_request()
    req_dict = json.loads(req.model_dump_json())
    req_dict["environment_metadata"]["fixture"]["supports_reset"] = False
    req_dict["environment_metadata"]["fixture"]["supports_observation"] = False

    mutated_req = CaseValidationRequest.model_validate(req_dict)
    resp = validate_candidate_case(mutated_req)

    assert resp.validation_status == ValidationStatus.TEST_NOT_READY
    assert any(r.code == "FIXTURE_RESET_NOT_SUPPORTED" for r in resp.reasons)
    assert any(r.code == "FIXTURE_OBSERVATION_NOT_SUPPORTED" for r in resp.reasons)


# ---------------------------------------------------------------------------
# 7. Recovery Budgets, Counting Semantics & Contradictory Contracts
# ---------------------------------------------------------------------------


def test_contradictory_attempt_budget_rejected():
    """
    Counting semantics: attempt 1 is initial call. max_retries must be strictly
    less than max_total_attempts.
    """
    req = build_valid_test_request()
    req_dict = json.loads(req.model_dump_json())
    # Setting max_retries >= max_total_attempts
    req_dict["recovery_contract"]["max_total_attempts"] = 2
    req_dict["recovery_contract"]["max_retries"] = 2

    # Pydantic model validator rejects budget incoherence
    with pytest.raises(
        ValueError, match="max_retries must be strictly less than max_total_attempts"
    ):
        RecoveryContract.model_validate(req_dict["recovery_contract"])


def test_fault_delay_exceeds_timeout_budget():
    """Fault delay >= recovery timeout budget makes recovery impossible on first call."""
    req = build_valid_test_request()
    req_dict = json.loads(req.model_dump_json())
    # Fault delay is 5000ms = 5.0s, set recovery timeout budget to 4.0s
    req_dict["recovery_contract"]["timeout_budget_seconds"] = 4.0

    mutated_req = CaseValidationRequest.model_validate(req_dict)
    resp = validate_candidate_case(mutated_req)

    assert resp.validation_status == ValidationStatus.TEST_NOT_READY
    assert any(r.code == "FAULT_DELAY_EXCEEDS_TIMEOUT_BUDGET" for r in resp.reasons)


def test_no_permitted_non_failure_outcomes():
    """Recovery contract must permit at least one non-failure terminal outcome."""
    req = build_valid_test_request()
    req_dict = json.loads(req.model_dump_json())
    req_dict["recovery_contract"]["permitted_terminal_outcomes"] = ["FAIL"]

    mutated_req = CaseValidationRequest.model_validate(req_dict)
    resp = validate_candidate_case(mutated_req)

    assert resp.validation_status == ValidationStatus.TEST_NOT_READY
    assert any(r.code == "NO_PERMITTED_NON_FAILURE_OUTCOME" for r in resp.reasons)


# ---------------------------------------------------------------------------
# 8. Sanitized 422 Without Echoing Canary Secrets
# ---------------------------------------------------------------------------


def test_sanitized_422_does_not_echo_canary_secret(client):
    """
    Malformed or invalid schema requests return HTTP 422 with sanitized detail,
    and MUST NOT echo canary secret contents in the response body.
    """
    canary = "CANARY_SECRET_TOP_CONFIDENTIAL_TOKEN_98765"
    malformed_payload = {
        "case": {
            "seed": canary,  # Type error: seed should be integer
            "unknown_extra_field": canary,
        },
        "secret_token": canary,
    }

    response = client.post("/api/v1/c3/cases/validate", json=malformed_payload)
    assert response.status_code == 422

    # CRITICAL: Verify canary string is NOT echoed anywhere in response text
    assert canary not in response.text

    # Detail must be a sanitized list without 'input' or 'ctx'
    detail = response.json().get("detail", [])
    assert isinstance(detail, list)
    for err in detail:
        assert "input" not in err
        assert "ctx" not in err
        assert "loc" in err
        assert "msg" in err
        assert "type" in err


def test_pydantic_rejects_boolean_as_attempt_count():
    """Booleans must not be accepted as integer attempt counts."""
    with pytest.raises(Exception):
        TriggerDefinition(
            tool_id="test", call_occurrence=True, hook=HookType.DURING_TRANSPORT
        )


def test_pydantic_rejects_unknown_fields():
    """Unknown fields are forbidden by strict configuration."""
    with pytest.raises(Exception):
        TriggerDefinition(
            tool_id="test",
            call_occurrence=1,
            hook=HookType.DURING_TRANSPORT,
            unexpected_field="disallowed",
        )


# ---------------------------------------------------------------------------
# 9. Schema Generation and Draft 2020-12 Compatibility
# ---------------------------------------------------------------------------


def test_json_schema_generation():
    """Pydantic v2 model_json_schema() generates Draft 2020-12 compliant schemas."""
    req_schema = CaseValidationRequest.model_json_schema()
    resp_schema = CaseValidationResponse.model_json_schema()
    catalog_schema = FaultCatalogResponse.model_json_schema()

    assert req_schema["type"] == "object"
    assert resp_schema["type"] == "object"
    assert catalog_schema["type"] == "object"

    # Must serialize to JSON cleanly
    json_req_str = json.dumps(req_schema)
    json_resp_str = json.dumps(resp_schema)
    assert len(json_req_str) > 100
    assert len(json_resp_str) > 100


# ---------------------------------------------------------------------------
# 10. No Database or Network Calls in C3 Foundation
# ---------------------------------------------------------------------------


def test_c3_foundation_makes_no_database_calls(client):
    """C3 endpoints and validator must not access database engine or get_db dependency."""
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    try:
        # 1. Fault catalog
        resp_cat = client.get("/api/v1/c3/fault-catalog")
        assert resp_cat.status_code == 200

        # 2. Case validate
        req = build_valid_test_request()
        resp_val = client.post(
            "/api/v1/c3/cases/validate", json=json.loads(req.model_dump_json())
        )
        assert resp_val.status_code == 200

        # Mock DB must NEVER have been called
        mock_db.execute.assert_not_called()
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 11. OpenAPI Registration & Preservation of Existing Routes
# ---------------------------------------------------------------------------


def test_openapi_routes_registered_and_health_routes_preserved(client):
    """
    OpenAPI specification contains the two C3 endpoints and retains the
    three existing health endpoints.
    """
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    # Original routes preserved
    assert "/" in paths
    assert "/health" in paths
    assert "/health/db" in paths

    # New C3 routes registered
    assert "/api/v1/c3/fault-catalog" in paths
    assert (
        "get" in paths["api/v1/c3/fault-catalog"]
        if "api/v1/c3/fault-catalog" in paths
        else "get" in paths["/api/v1/c3/fault-catalog"]
    )

    assert "/api/v1/c3/cases/validate" in paths
    assert (
        "post" in paths["api/v1/c3/cases/validate"]
        if "api/v1/c3/cases/validate" in paths
        else "post" in paths["/api/v1/c3/cases/validate"]
    )

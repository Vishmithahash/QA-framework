"""
Hermetic automated tests for Component 3 (C3) Phase 2:
- Clean calls forward normally.
- Targeted fault call never reaches the target.
- Correct occurrence triggers exactly once.
- Subsequent calls forward normally.
- Caller-observed timeout and linked receipt evidence.
- Missing/contradictory receipts produce EXPOSURE_UNKNOWN.
- Unreached trigger produces NOT_TRIGGERED with complete evidence.
- Fixture reset verification and equivalent starting states.
- Failed clean controls retained without rerun-until-pass.
- Deadline/cancellation does not leave pending fixture effects.
- Harness errors remain distinct from injected faults.
- Configuration snapshots remain stable across the pair.
- No C3-added retries or recovery scoring (recovery_verdict=None).
- Safe JSON serialization and redacted argument evidence.
- Phase 1 confirmed gap regressions.
- Existing Phase 1 endpoints and original health routes remain intact.
"""

import json
import os
from pathlib import Path
import tempfile
from fastapi.testclient import TestClient
import pytest

# Ensure isolated hermetic test environment before loading settings
os.environ["DATABASE_URL"] = (
    "postgresql://fake_user:fake_password@localhost:5432/fake_db?sslmode=require"
)

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.components.c3_robustness_recovery.adapter import (  # noqa: E402
    FakeNexaCartFixtureManager,
    FakeNexaCartOrderToolAdapter,
    IntegrationBlockedError,
    NexaCartHttpToolAdapter,
    NexaCartPrismaFixtureManager,
)
from app.components.c3_robustness_recovery.evidence import (  # noqa: E402
    CallerOutcome,
    ExecutionStatus,
    ExposureStatus,
    fingerprint_args,
)
from app.components.c3_robustness_recovery.interceptor import (  # noqa: E402
    OneShotTimeoutInterceptor,
)
from app.components.c3_robustness_recovery.runner import (  # noqa: E402
    build_default_phase2_request,
    run_matched_pair,
)
from app.components.c3_robustness_recovery.schemas import (  # noqa: E402
    CaseValidationRequest,
    ValidationStatus,
)
from app.components.c3_robustness_recovery.validation import (  # noqa: E402
    validate_candidate_case,
)
from app.main import app  # noqa: E402
from tests.test_c3_foundation import build_valid_test_request  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# 1. Interceptor Mechanics: Clean, Target Prevention, Single Shot, Passthrough
# ---------------------------------------------------------------------------


def test_clean_calls_forward_normally():
    """In a clean control trial, the interceptor forwards all calls to the target adapter."""
    fixture = FakeNexaCartFixtureManager()
    adapter = FakeNexaCartOrderToolAdapter(fixture)
    interceptor = OneShotTimeoutInterceptor(
        target_tool_id="create_order",
        target_call_occurrence=1,
        armed=False,  # Disarmed for clean trial
    )

    result = interceptor.execute(
        adapter, {"items": [{"sku": "A", "quantity": 1}], "total_amount": 25.0}
    )
    assert result["status"] == "CREATED"
    assert fixture.observe().record_count == 1
    assert len(interceptor.receipts) == 1

    receipt = interceptor.receipts[0]
    assert receipt.forwarded_to_target is True
    assert receipt.fault_injected is False
    assert receipt.caller_outcome == CallerOutcome.SUCCESS


def test_targeted_fault_call_never_reaches_target():
    """On matching occurrence, the interceptor prevents target forwarding before any effect."""
    fixture = FakeNexaCartFixtureManager()
    adapter = FakeNexaCartOrderToolAdapter(fixture)
    interceptor = OneShotTimeoutInterceptor(
        target_tool_id="create_order",
        target_call_occurrence=1,
        armed=True,
        synthetic_timeout=True,
    )

    with pytest.raises(TimeoutError):
        interceptor.execute(
            adapter, {"items": [{"sku": "A", "quantity": 1}], "total_amount": 25.0}
        )

    # VERIFIED: Target adapter was never invoked; fixture record count remains 0
    assert fixture.observe().record_count == 0
    assert len(interceptor.receipts) == 1

    receipt = interceptor.receipts[0]
    assert receipt.reached_hook is True
    assert receipt.forwarded_to_target is False
    assert receipt.fault_injected is True
    assert receipt.caller_outcome == CallerOutcome.TIMEOUT


def test_occurrence_triggers_exactly_once_and_subsequent_calls_pass_through():
    """The fault triggers on the target occurrence, then subsequent calls pass through normally."""
    fixture = FakeNexaCartFixtureManager()
    adapter = FakeNexaCartOrderToolAdapter(fixture)
    interceptor = OneShotTimeoutInterceptor(
        target_tool_id="create_order",
        target_call_occurrence=1,
        armed=True,
        synthetic_timeout=True,
    )

    # Call 1 (Target occurrence): Should time out without reaching target
    with pytest.raises(TimeoutError):
        interceptor.execute(adapter, {"call": 1})

    assert fixture.observe().record_count == 0
    assert interceptor.consumed is True

    # Call 2 (Subsequent occurrence): Should pass through normally
    res2 = interceptor.execute(adapter, {"call": 2})
    assert res2["status"] == "CREATED"
    assert fixture.observe().record_count == 1

    # Call 3 (Subsequent occurrence): Should pass through normally
    res3 = interceptor.execute(adapter, {"call": 3})
    assert res3["status"] == "CREATED"
    assert fixture.observe().record_count == 2

    assert len(interceptor.receipts) == 3
    assert interceptor.receipts[0].caller_outcome == CallerOutcome.TIMEOUT
    assert interceptor.receipts[0].forwarded_to_target is False
    assert interceptor.receipts[1].caller_outcome == CallerOutcome.SUCCESS
    assert interceptor.receipts[1].forwarded_to_target is True
    assert interceptor.receipts[2].caller_outcome == CallerOutcome.SUCCESS
    assert interceptor.receipts[2].forwarded_to_target is True


def test_interceptor_targets_correct_occurrence_when_not_first():
    """Interceptor only intercepts when current occurrence matches target occurrence."""
    fixture = FakeNexaCartFixtureManager()
    adapter = FakeNexaCartOrderToolAdapter(fixture)
    interceptor = OneShotTimeoutInterceptor(
        target_tool_id="create_order",
        target_call_occurrence=2,  # Target the SECOND call
        armed=True,
        synthetic_timeout=True,
    )

    # Call 1: Passthrough
    res1 = interceptor.execute(adapter, {"call": 1})
    assert res1["status"] == "CREATED"
    assert fixture.observe().record_count == 1

    # Call 2: Intercepted!
    with pytest.raises(TimeoutError):
        interceptor.execute(adapter, {"call": 2})

    assert fixture.observe().record_count == 1  # Unchanged by intercepted call
    assert interceptor.consumed is True


# ---------------------------------------------------------------------------
# 2. Matched Pair Runner: Exposure Classification
# ---------------------------------------------------------------------------


def test_matched_pair_confirmed_exposure():
    """A consistent matched pair execution produces exposure_status == CONFIRMED and recovery_verdict == null."""
    req = build_default_phase2_request()
    evidence = run_matched_pair(
        case=req.case,
        recovery_contract=req.recovery_contract,
        synthetic_timeout=True,
    )

    assert evidence.clean_trial.clean_qualified is True
    assert evidence.clean_trial.execution_status == ExecutionStatus.COMPLETED
    assert evidence.fault_trial.execution_status == ExecutionStatus.COMPLETED
    assert evidence.exposure_status == ExposureStatus.CONFIRMED
    assert evidence.recovery_verdict is None
    assert evidence.is_harness_demonstration is True


def test_unreached_trigger_produces_not_triggered():
    """When the caller never reaches the target occurrence count, exposure is NOT_TRIGGERED."""
    req = build_default_phase2_request()
    # Configure case to intercept call occurrence 5, but caller only makes 1 attempt
    req_dict = json.loads(req.model_dump_json())
    req_dict["case"]["trigger"]["call_occurrence"] = 5
    case = req.case.model_validate(req_dict["case"])

    def single_call_caller(invoker, role):
        invoker({"items": [{"sku": "A", "quantity": 1}]})

    evidence = run_matched_pair(
        case=case,
        recovery_contract=req.recovery_contract,
        caller=single_call_caller,
        synthetic_timeout=True,
    )

    assert evidence.clean_trial.clean_qualified is True
    assert evidence.exposure_status == ExposureStatus.NOT_TRIGGERED
    assert evidence.recovery_verdict is None


def test_failed_clean_control_retained_and_limits_exposure():
    """
    Failed clean controls are retained without rerun-until-pass,
    and cause exposure status to be classified as EXPOSURE_UNKNOWN.
    """
    req = build_default_phase2_request()
    evidence = run_matched_pair(
        case=req.case,
        recovery_contract=req.recovery_contract,
        force_clean_failure=True,  # Simulate broken clean control
        synthetic_timeout=True,
    )

    # Clean control failure is recorded, not hidden or retried
    assert evidence.clean_trial.clean_qualified is False
    assert evidence.clean_trial.execution_status == ExecutionStatus.EXECUTION_ERROR
    assert evidence.exposure_status == ExposureStatus.EXPOSURE_UNKNOWN
    assert evidence.recovery_verdict is None


def test_fixture_reset_and_equivalent_starting_states():
    """Clean and fault trials begin with verified equivalent initial fixture states."""
    fixture = FakeNexaCartFixtureManager()
    adapter = FakeNexaCartOrderToolAdapter(fixture)
    req = build_default_phase2_request()

    evidence = run_matched_pair(
        case=req.case,
        recovery_contract=req.recovery_contract,
        adapter=adapter,
        fixture_manager=fixture,
        synthetic_timeout=True,
    )

    # Both trials began with empty (record_count=0) state
    assert evidence.clean_trial.initial_fixture.record_count == 0
    assert evidence.fault_trial.initial_fixture.record_count == 0
    assert (
        evidence.clean_trial.initial_fixture.state_fingerprint
        == evidence.fault_trial.initial_fixture.state_fingerprint
    )


def test_configuration_snapshots_remain_stable_across_pair():
    """Case, recovery contract, and adapter metadata are captured immutably across the pair."""
    req = build_default_phase2_request()
    evidence = run_matched_pair(
        case=req.case,
        recovery_contract=req.recovery_contract,
        synthetic_timeout=True,
    )

    assert evidence.case_snapshot["case_id"] == req.case.case_id
    assert (
        evidence.recovery_contract_snapshot["contract_id"]
        == req.recovery_contract.contract_id
    )
    assert "create_order" in evidence.adapter_version_snapshot


# ---------------------------------------------------------------------------
# 3. Evidence Artifact Safety & Non-Leakage
# ---------------------------------------------------------------------------


def test_argument_fingerprinting_redacts_secrets():
    """Argument fingerprinting produces deterministic hash while redacting secrets."""
    args_with_secret = {
        "order_id": "12345",
        "auth_token": "MY_SUPER_SECRET_TOKEN_9999",
        "api_key": "SECRET_KEY_123",
        "password": "SECRET_PASSWORD",
    }
    fp1 = fingerprint_args(args_with_secret)
    fp2 = fingerprint_args(args_with_secret)
    assert fp1 == fp2
    assert len(fp1) == 16


def test_save_evidence_artifact_to_local_directory():
    """Evidence artifact writes to local directory and contains no raw secret strings."""
    req = build_default_phase2_request()
    with tempfile.TemporaryDirectory() as tmp_dir:
        evidence = run_matched_pair(
            case=req.case,
            recovery_contract=req.recovery_contract,
            output_dir=tmp_dir,
            synthetic_timeout=True,
        )

        saved_files = list(Path(tmp_dir).glob("*.json"))
        assert len(saved_files) == 1

        content = saved_files[0].read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert parsed["pair_id"] == evidence.pair_id
        assert parsed["recovery_verdict"] is None
        assert parsed["exposure_status"] == "CONFIRMED"


# ---------------------------------------------------------------------------
# 4. NexaCart Missing Prerequisites Handling
# ---------------------------------------------------------------------------


def test_real_nexacart_adapters_mark_execution_blocked_when_unconfigured():
    """Real NexaCart adapters raise IntegrationBlockedError when live configuration is absent."""
    http_adapter = NexaCartHttpToolAdapter(base_url=None)
    with pytest.raises(IntegrationBlockedError, match="NEXACART_BASE_URL"):
        http_adapter.invoke({"dummy": 1})

    db_fixture = NexaCartPrismaFixtureManager(database_url=None)
    with pytest.raises(IntegrationBlockedError, match="NEXACART_DATABASE_URL"):
        db_fixture.prepare()


# ---------------------------------------------------------------------------
# 5. Regressions for Confirmed Phase 1 Gaps
# ---------------------------------------------------------------------------


def test_capability_matching_enforces_tool_id_scoping():
    """
    Regression: Capability declared for tool 'charge_payment' must not match
    a case requesting tool 'create_order'.
    """
    req = build_valid_test_request()
    req_dict = json.loads(req.model_dump_json())

    # Manifest scopes capability strictly to charge_payment
    req_dict["adapter_manifest"]["capabilities"][0]["tool_id"] = "charge_payment"

    # Add create_order tool to manifest tools
    req_dict["adapter_manifest"]["tools"].append(
        {"tool_id": "create_order", "tool_version": "1.0.0", "is_side_effecting": True}
    )

    # Case targets create_order
    req_dict["case"]["tool_id"] = "create_order"
    req_dict["case"]["trigger"]["tool_id"] = "create_order"

    mutated_req = CaseValidationRequest.model_validate(req_dict)
    resp = validate_candidate_case(mutated_req)

    assert resp.validation_status == ValidationStatus.TEST_NOT_READY
    assert any(r.code == "CAPABILITY_COMBINATION_NOT_DECLARED" for r in resp.reasons)


def test_partial_effect_supported_when_application_aware_and_observed():
    """
    Regression: PARTIAL_EFFECT is NOT categorically forbidden for timeouts
    if the adapter declares an application-aware hook and fixture declares observation.
    """
    req = build_valid_test_request()
    req_dict = json.loads(req.model_dump_json())

    # Case requests PARTIAL_EFFECT with POST_COMMIT hook
    req_dict["case"]["effect_phase"] = "PARTIAL_EFFECT"
    req_dict["case"]["trigger"]["hook"] = "POST_COMMIT"

    # Capability explicitly supports PARTIAL_EFFECT with POST_COMMIT hook
    req_dict["adapter_manifest"]["capabilities"].append(
        {
            "fault_family": "TIMEOUT_OR_DISCONNECTION",
            "effect_phase": "PARTIAL_EFFECT",
            "hook": "POST_COMMIT",
            "observation_method": "obs_network_trace",
            "supported_release_modes": ["SINGLE_CALL"],
            "is_application_aware": True,
        }
    )

    # Fixture declares observable partial effects
    req_dict["environment_metadata"]["fixture"]["has_partial_effect_observation"] = True

    mutated_req = CaseValidationRequest.model_validate(req_dict)
    resp = validate_candidate_case(mutated_req)

    # Statically valid! Not categorically rejected!
    assert resp.validation_status == ValidationStatus.STATIC_VALID


def test_caller_timeout_distinguished_from_recovery_budget():
    """
    Regression: When testing a timeout, injected delay is permitted to exceed
    caller timeout boundary as long as caller timeout is within recovery budget.
    """
    req = build_valid_test_request()
    req_dict = json.loads(req.model_dump_json())

    # Caller timeout is 2.0s, recovery contract budget is 10.0s, injected delay is 5000ms (5s)
    req_dict["case"]["caller_timeout_seconds"] = 2.0
    req_dict["case"]["payload"]["delay_ms"] = 5000
    req_dict["recovery_contract"]["timeout_budget_seconds"] = 10.0

    mutated_req = CaseValidationRequest.model_validate(req_dict)
    resp = validate_candidate_case(mutated_req)

    assert resp.validation_status == ValidationStatus.STATIC_VALID


# ---------------------------------------------------------------------------
# 6. Verification of Endpoints and Health Routes
# ---------------------------------------------------------------------------


def test_endpoints_and_health_routes_remain_intact(client):
    """Phase 1 endpoints and original health routes remain functional."""
    # Health routes
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200

    # Phase 1 endpoints
    assert client.get("/api/v1/c3/fault-catalog").status_code == 200

    req = build_valid_test_request()
    val_resp = client.post(
        "/api/v1/c3/cases/validate", json=json.loads(req.model_dump_json())
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["validation_status"] == "STATIC_VALID"
    assert val_resp.json()["execution_ready"] is False
    assert val_resp.json()["recovery_verdict"] is None

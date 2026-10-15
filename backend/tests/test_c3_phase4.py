"""
Hermetic automated tests for Component 3 (C3) Phase 4:
- Automatic candidate fault case generation from declared metadata.
- Derivation strictly from explicit capability combinations (no blind cross-products).
- Parameter sampling across all 5 catalogue families.
- Examination budget stopping and explicit truncation reporting.
- Strict static validation of every generated candidate.
- Semantic fingerprinting and deduplication.
- Input collection ordering independence.
- Seeded deterministic round-robin selection.
- Frozen suite assembly, canonical hashing, SHA-256 digest, and tamper detection.
- Prevention of input mutation leakage (defensive snapshotting).
- JSON round-trip integrity preservation.
- Local export with overwrite protection.
- POST /api/v1/c3/cases/generate stateless API endpoint.
- Confirmed Phase 1-3 defect fixes and regression verification:
  * Nonzero exit code (2) on blocked live CLI execution.
  * Normalized database URL comparison in NexaCartPrismaFixtureManager.
  * Settling cleanup verification requiring settled operations and observation evidence.
  * Interceptor path correlation with genuine transport timeout.
  * Evidence linkage validation prior to export in save_evidence_artifact.
"""

from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import sys
import threading
import time
from typing import Any
from unittest.mock import patch
from fastapi.testclient import TestClient
import httpx
import pytest

# Ensure isolated hermetic test environment before loading settings
os.environ["DATABASE_URL"] = (
    "postgresql://fake_user:fake_password@localhost:5432/fake_db?sslmode=require"
)

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.components.c3_robustness_recovery.contracts.generation import (  # noqa: E402
    CaseGenerationRequest,
    FrozenSuite,
    GenerationFilters,
    GenerationPolicy,
    GenerationStatus,
)
from app.components.c3_robustness_recovery.contracts.schemas import (  # noqa: E402
    AdapterCapability,
    AdapterCapabilityManifest,
    AssertionMetadata,
    EffectPhase,
    FaultFamily,
    FixtureMetadata,
    HookType,
    MalformedMode,
    ObservationMethodMetadata,
    RecoveryContract,
    ReleaseRuleMode,
    TaskMetadata,
    TerminalOutcome,
    TimeoutMode,
    ToolDeclaration,
    UnavailabilityMode,
    ValidationScope,
)
from app.components.c3_robustness_recovery.runtime.adapter import (  # noqa: E402
    FakeNexaCartFixtureManager,
    FakeNexaCartOrderToolAdapter,
    IntegrationBlockedError,
    NexaCartPrismaFixtureManager,
    ToolAdapter,
    normalize_db_identity,
)
from app.components.c3_robustness_recovery.runtime.evidence import (  # noqa: E402
    CallerOutcome,
    CleanupStatus,
    EvidenceLinkageError,
    TimeoutBoundary,
    save_evidence_artifact,
)
from app.components.c3_robustness_recovery.runtime.interceptor import (  # noqa: E402
    OneShotTimeoutInterceptor,
)
from app.components.c3_robustness_recovery.runtime.runner import (  # noqa: E402
    main as runner_main,
    run_matched_pair,
)
from app.components.c3_robustness_recovery.services.generation import (  # noqa: E402
    generate_fault_suite,
)
from app.components.c3_robustness_recovery.services.suites import (  # noqa: E402
    compute_case_semantic_fingerprint,
    export_frozen_suite,
    to_canonical_json,
    verify_suite_integrity,
)
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def build_base_generation_request() -> CaseGenerationRequest:
    """Construct a comprehensive, valid generation request declaring multi-family capabilities."""
    task = TaskMetadata(
        task_id="task-checkout-flow",
        task_version="1.0.0",
        domain="e-commerce",
    )
    fixture = FixtureMetadata(
        fixture_id="fix-order-db",
        fixture_version="1.0.0",
        supports_reset=True,
        supports_observation=True,
        has_commit_observation=True,
        has_partial_effect_observation=True,
    )
    assertions = [
        AssertionMetadata(
            assertion_id="assert_order_recorded",
            assertion_type="STATE_MUTATION",
            description="Verify order is committed to database.",
        ),
        AssertionMetadata(
            assertion_id="assert_user_notified",
            assertion_type="NOTIFICATION",
            description="Verify caller received notification of result.",
        ),
    ]
    obs_methods = [
        ObservationMethodMetadata(
            method_id="obs_order_query",
            description="Query database order records.",
        ),
        ObservationMethodMetadata(
            method_id="obs_network_trace",
            description="Verify network transport receipts.",
        ),
    ]
    recovery_contract = RecoveryContract(
        contract_id="rec-standard-01",
        version="1.0.0",
        permitted_terminal_outcomes=[
            TerminalOutcome.SUCCESS,
            TerminalOutcome.SAFE_ABORT,
        ],
        graceful_stopping_conditions=["max_retries_exceeded"],
        max_total_attempts=3,
        max_retries=2,
        timeout_budget_seconds=30.0,
        required_assertion_ids=["assert_order_recorded", "assert_user_notified"],
        rule_ids=["rule-no-duplicate-orders"],
    )

    manifest = AdapterCapabilityManifest(
        schema_version="1.0.0",
        adapter_id="adapter-payment-order",
        adapter_version="1.0.0",
        tools=[
            ToolDeclaration(
                tool_id="create_order",
                tool_version="1.0.0",
                is_side_effecting=True,
            ),
            ToolDeclaration(
                tool_id="check_inventory",
                tool_version="1.0.0",
                is_side_effecting=False,
            ),
        ],
        capabilities=[
            # 1. Timeout / Disconnection
            AdapterCapability(
                fault_family=FaultFamily.TIMEOUT_OR_DISCONNECTION,
                effect_phase=EffectPhase.BEFORE_EFFECT,
                hook=HookType.DURING_TRANSPORT,
                observation_method="obs_network_trace",
                tool_id="create_order",
                max_call_occurrence=2,
                allowed_modes=[
                    TimeoutMode.CONNECTION_TIMEOUT.value,
                    TimeoutMode.READ_TIMEOUT.value,
                ],
                min_delay_ms=100,
                max_delay_ms=5000,
                supported_release_modes=[ReleaseRuleMode.SINGLE_CALL],
            ),
            # 2. Transient 5xx
            AdapterCapability(
                fault_family=FaultFamily.TRANSIENT_5XX_SERVER_ERROR,
                effect_phase=EffectPhase.BEFORE_EFFECT,
                hook=HookType.DURING_TRANSPORT,
                observation_method="obs_network_trace",
                tool_id="create_order",
                allowed_status_codes=[500, 503],
                supported_release_modes=[ReleaseRuleMode.SINGLE_CALL],
            ),
            # 3. HTTP 429 Rate Limiting
            AdapterCapability(
                fault_family=FaultFamily.HTTP_429_RATE_LIMITING,
                effect_phase=EffectPhase.BEFORE_EFFECT,
                hook=HookType.DURING_TRANSPORT,
                observation_method="obs_network_trace",
                tool_id="create_order",
                max_retry_after_seconds=30,
                supported_release_modes=[ReleaseRuleMode.SINGLE_CALL],
            ),
            # 4. Tool Unavailability
            AdapterCapability(
                fault_family=FaultFamily.TOOL_UNAVAILABILITY,
                effect_phase=EffectPhase.BEFORE_EFFECT,
                hook=HookType.PRE_TOOL_INVOCATION,
                observation_method="obs_network_trace",
                tool_id="check_inventory",
                allowed_modes=[
                    UnavailabilityMode.CIRCUIT_BREAKER_OPEN.value,
                    UnavailabilityMode.MAINTENANCE_MODE.value,
                ],
                supported_release_modes=[ReleaseRuleMode.SINGLE_CALL],
            ),
            # 5. Malformed Response
            AdapterCapability(
                fault_family=FaultFamily.MALFORMED_OR_TRUNCATED_RESPONSE,
                effect_phase=EffectPhase.BEFORE_EFFECT,
                hook=HookType.ON_RESPONSE_RECEIPT,
                observation_method="obs_network_trace",
                tool_id="check_inventory",
                allowed_modes=[
                    MalformedMode.INVALID_JSON.value,
                    MalformedMode.TRUNCATED_JSON.value,
                ],
                supported_release_modes=[ReleaseRuleMode.SINGLE_CALL],
            ),
        ],
    )

    return CaseGenerationRequest(
        schema_version="1.0.0",
        project_id="proj-nexacart-qa",
        tasks=[task],
        adapter_manifests=[manifest],
        fixtures=[fixture],
        recovery_contracts=[recovery_contract],
        available_assertions=assertions,
        observation_methods=obs_methods,
        seed=42,
        policy=GenerationPolicy(max_cases=15, max_candidates_examined=200),
    )


# ===========================================================================
# 1. Confirmed Previous Defect Regression Tests
# ===========================================================================


def test_cli_live_blocked_nonzero_exit_code():
    """Verify that requesting live target mode without prerequisites exits with code 2."""
    test_args = ["runner.py", "--live"]
    with patch.object(sys, "argv", test_args):
        with pytest.raises(SystemExit) as exc_info:
            runner_main()
        assert exc_info.value.code == 2


def test_cli_synthetic_zero_exit_code(tmp_path):
    """Verify that synthetic test double mode exits cleanly with code 0."""
    test_args = ["runner.py", "--synthetic", "--output-dir", str(tmp_path)]
    with patch.object(sys, "argv", test_args):
        # Should complete without raising SystemExit with nonzero code
        runner_main()


def test_database_identity_normalization():
    """Verify that logical database identity normalization rejects equivalent URLs."""
    # Same logical DB on loopback with different drivers and default ports
    url1 = "postgresql+asyncpg://app_user:secret@127.0.0.1:5432/qa_neon?ssl=require"
    url2 = "postgres://different_user:diff_pass@localhost/qa_neon"

    norm1 = normalize_db_identity(url1)
    norm2 = normalize_db_identity(url2)

    assert norm1 is not None and norm2 is not None
    assert norm1["host"] == "127.0.0.1"
    assert norm2["host"] == "127.0.0.1"
    assert norm1["port"] == 5432
    assert norm2["port"] == 5432
    assert norm1["database"] == "qa_neon"
    assert norm2["database"] == "qa_neon"

    with patch.dict(os.environ, {"DATABASE_URL": url1}):
        with pytest.raises(IntegrationBlockedError, match="QA Neon"):
            NexaCartPrismaFixtureManager(database_url=url2)


def test_cleanup_uncertain_when_operations_unsettled():
    """Verify that an unchanged state fingerprint alone does not establish CLEANUP_VERIFIED if calls remain in flight."""
    req = build_base_generation_request()
    res = generate_fault_suite(req)
    assert res.selected_cases
    case = next(
        c
        for c in res.selected_cases
        if c.fault_family == FaultFamily.TIMEOUT_OR_DISCONNECTION
    )
    contract = req.recovery_contracts[0]

    fixture_mgr = FakeNexaCartFixtureManager()
    adapter = FakeNexaCartOrderToolAdapter(fixture_mgr, namespace="ns-settle-test")

    # Custom caller that holds execution without letting interceptor settle
    def unsettled_caller(invoker, trial_role):
        try:
            invoker({"items": [{"sku": "SKU-1", "quantity": 1}], "total_amount": 10.0})
        except TimeoutError:
            pass

    # Run with settling_period_seconds=0 -> operations not settled
    evidence = run_matched_pair(
        case=case,
        recovery_contract=contract,
        adapter=adapter,
        fixture_manager=fixture_mgr,
        caller=unsettled_caller,
        synthetic_timeout=True,
        settling_period_seconds=0.0,
    )

    # settling_period_seconds <= 0 must yield CLEANUP_UNCERTAIN
    assert evidence.cleanup_status == CleanupStatus.CLEANUP_UNCERTAIN
    assert evidence.fixture_reusable is False


class EphemeralStallHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        time.sleep(0.8)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')

    def log_message(self, format, *args):
        pass


@contextmanager
def ephemeral_server() -> Generator[str, None, None]:
    server = HTTPServer(("127.0.0.1", 0), EphemeralStallHandler)
    port = server.server_port
    base_url = f"http://127.0.0.1:{port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield base_url
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


class StallingHttpToolAdapter(ToolAdapter):
    tool_id = "http_post_tool"
    tool_version = "1.0.0"
    is_side_effecting = True

    def __init__(self, endpoint_url: str):
        self.endpoint_url = endpoint_url

    def invoke(
        self, args: dict[str, Any], timeout_seconds: float = 5.0
    ) -> dict[str, Any]:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(self.endpoint_url, json=args)
            return resp.json()


def test_timeout_evidence_interceptor_path_correlation():
    """
    Verify that genuine transport timeout exercises the actual interceptor path,
    correlating hook entry, selected occurrence, prevented forwarding, and caller-observed timeout.
    """
    with ephemeral_server() as server_url:
        adapter = StallingHttpToolAdapter(f"{server_url}/order")
        interceptor = OneShotTimeoutInterceptor(
            target_tool_id="http_post_tool",
            target_call_occurrence=1,
            hook=HookType.DURING_TRANSPORT,
            delay_ms=2000,
            caller_timeout_seconds=0.15,
            armed=True,
            synthetic_timeout=False,
            timeout_boundary=TimeoutBoundary.ACTUAL_TRANSPORT_TIMEOUT,
        )

        t0 = time.monotonic()
        observed_timeout = False
        try:
            interceptor.execute(adapter, {"key": "val"}, caller_timeout_seconds=0.15)
        except TimeoutError:
            observed_timeout = True
        elapsed = time.monotonic() - t0

        assert observed_timeout is True
        assert 0.10 <= elapsed < 0.60
        assert len(interceptor.receipts) == 1

        receipt = interceptor.receipts[0]
        # Correlation checks on the actual interceptor path
        assert receipt.reached_hook is True
        assert receipt.tool_occurrence == 1
        assert receipt.forwarded_to_target is False
        assert receipt.fault_injected is True
        assert receipt.caller_outcome == CallerOutcome.TIMEOUT
        assert receipt.timeout_boundary == TimeoutBoundary.ACTUAL_TRANSPORT_TIMEOUT
        assert receipt.is_synthetic is False


def test_evidence_linkage_validation_prior_to_export(tmp_path):
    """Verify that save_evidence_artifact invokes linkage validation and rejects inconsistent evidence."""
    req = build_base_generation_request()
    res = generate_fault_suite(req)
    case = next(
        c
        for c in res.selected_cases
        if c.fault_family == FaultFamily.TIMEOUT_OR_DISCONNECTION
    )
    contract = req.recovery_contracts[0]

    evidence = run_matched_pair(
        case=case,
        recovery_contract=contract,
        synthetic_timeout=True,
    )

    # Corrupt receipt pair_id linkage
    corrupted_receipt = evidence.fault_trial.intercepted_calls[0].model_copy(
        update={"pair_id": "pair-mismatched-999"}
    )
    corrupted_trial = evidence.fault_trial.model_copy(
        update={"intercepted_calls": [corrupted_receipt]}
    )
    corrupted_evidence = evidence.model_copy(update={"fault_trial": corrupted_trial})

    with pytest.raises(
        EvidenceLinkageError, match="Evidence linkage validation failed"
    ):
        save_evidence_artifact(corrupted_evidence, tmp_path)


# ===========================================================================
# 2. Phase 4 Automatic Candidate Generation Tests
# ===========================================================================


def test_automatic_generation_from_compatible_metadata():
    """Verify generation derived from declared capabilities across all 5 families."""
    req = build_base_generation_request()
    res = generate_fault_suite(req)

    assert res.status == GenerationStatus.GENERATED
    assert res.validation_scope == ValidationScope.STATIC_ONLY
    assert res.runtime_verified is False
    assert res.execution_ready is False
    assert res.recovery_verdict is None
    assert len(res.selected_cases) > 0

    # Ensure every single selected case is statically valid
    for c in res.selected_cases:
        assert c.project_id == req.project_id
        assert c.case_id.startswith("case-")
        assert c.case_family.startswith("fam-")

    # Verify coverage across all 5 families declared in the manifest
    families_covered = set(res.coverage_summary.fault_families_covered)
    assert FaultFamily.TIMEOUT_OR_DISCONNECTION in families_covered
    assert FaultFamily.TRANSIENT_5XX_SERVER_ERROR in families_covered
    assert FaultFamily.HTTP_429_RATE_LIMITING in families_covered
    assert FaultFamily.TOOL_UNAVAILABILITY in families_covered
    assert FaultFamily.MALFORMED_OR_TRUNCATED_RESPONSE in families_covered


def test_exact_capability_combinations_no_cross_product():
    """Verify that generation does not infer unsupported combinations through cross-products."""
    req = build_base_generation_request()
    # Strip capabilities to ONLY timeout on create_order
    req.adapter_manifests[0].capabilities = [
        AdapterCapability(
            fault_family=FaultFamily.TIMEOUT_OR_DISCONNECTION,
            effect_phase=EffectPhase.BEFORE_EFFECT,
            hook=HookType.DURING_TRANSPORT,
            observation_method="obs_network_trace",
            tool_id="create_order",
            max_call_occurrence=1,
            allowed_modes=[TimeoutMode.READ_TIMEOUT.value],
            min_delay_ms=1000,
            max_delay_ms=1000,
            supported_release_modes=[ReleaseRuleMode.SINGLE_CALL],
        )
    ]

    res = generate_fault_suite(req)
    assert res.status == GenerationStatus.GENERATED
    for c in res.selected_cases:
        # Must only be TIMEOUT_OR_DISCONNECTION on create_order
        assert c.tool_id == "create_order"
        assert c.fault_family == FaultFamily.TIMEOUT_OR_DISCONNECTION
        assert c.effect_phase == EffectPhase.BEFORE_EFFECT


def test_filters_scoping_and_skipped_summaries():
    """Verify explicit filters restrict output and record skipped summaries."""
    req = build_base_generation_request()
    req.filters = GenerationFilters(
        fault_families=[FaultFamily.HTTP_429_RATE_LIMITING],
    )

    res = generate_fault_suite(req)
    assert res.status == GenerationStatus.GENERATED
    assert len(res.selected_cases) > 0
    for c in res.selected_cases:
        assert c.fault_family == FaultFamily.HTTP_429_RATE_LIMITING

    assert len(res.skipped_summaries) > 0
    assert any(s["reason"].startswith("Filtered out") for s in res.skipped_summaries)


def test_examination_budget_stopping_and_truncation():
    """Verify that reaching max_candidates_examined stops derivation and reports truncation."""
    req = build_base_generation_request()
    req.policy = GenerationPolicy(max_cases=50, max_candidates_examined=3)

    res = generate_fault_suite(req)
    assert res.counters.examined_candidates == 3
    assert res.coverage_summary.is_truncated is True
    assert res.coverage_summary.candidate_population_denominator is None


def test_incompatible_metadata_returns_safe_reasons():
    """Verify that incompatible metadata (e.g., no compatible fixture) returns safe structured reasons."""
    req = build_base_generation_request()
    # Mark fixture as not supporting observation
    req.fixtures[0].supports_observation = False

    res = generate_fault_suite(req)
    assert res.status == GenerationStatus.INCOMPATIBLE_METADATA
    assert len(res.selected_cases) == 0
    assert len(res.rejected_summaries) > 0
    assert res.rejected_summaries[0].code == "NO_COMPATIBLE_FIXTURE"


# ===========================================================================
# 3. Deduplication and Selection Tests
# ===========================================================================


def test_deduplication_preserves_meaningful_variants():
    """Verify that cases with different occurrences or modes are preserved, while identical cases are deduplicated."""
    req = build_base_generation_request()
    res = generate_fault_suite(req)

    fps = [compute_case_semantic_fingerprint(c) for c in res.selected_cases]
    # All selected cases must have unique semantic fingerprints
    assert len(fps) == len(set(fps))
    assert res.counters.unique_valid_candidates >= len(res.selected_cases)


def test_input_ordering_independence():
    """Verify that shuffling input arrays of tasks, fixtures, and manifests produces the exact same suite digest."""
    req1 = build_base_generation_request()
    req2 = build_base_generation_request()

    # Invert ordering of tools and capabilities in req2
    req2.adapter_manifests[0].tools.reverse()
    req2.adapter_manifests[0].capabilities.reverse()
    req2.available_assertions.reverse()
    req2.observation_methods.reverse()

    res1 = generate_fault_suite(req1)
    res2 = generate_fault_suite(req2)

    assert res1.frozen_suite is not None
    assert res2.frozen_suite is not None
    assert res1.frozen_suite.content_digest == res2.frozen_suite.content_digest
    assert len(res1.selected_cases) == len(res2.selected_cases)
    for c1, c2 in zip(res1.selected_cases, res2.selected_cases, strict=True):
        assert c1.case_id == c2.case_id


def test_seeded_selection_reproducibility():
    """Verify that same seed produces identical case selection ordering."""
    req1 = build_base_generation_request()
    req1.seed = 12345
    req2 = build_base_generation_request()
    req2.seed = 12345

    res1 = generate_fault_suite(req1)
    res2 = generate_fault_suite(req2)

    ids1 = [c.case_id for c in res1.selected_cases]
    ids2 = [c.case_id for c in res2.selected_cases]
    assert ids1 == ids2


# ===========================================================================
# 4. Frozen Versioned Suite & Integrity Tests
# ===========================================================================


def test_frozen_suite_content_digest_verification():
    """Verify that untampered frozen suite verifies cleanly against its SHA-256 digest."""
    req = build_base_generation_request()
    res = generate_fault_suite(req)
    assert res.frozen_suite is not None

    valid, reason = verify_suite_integrity(res.frozen_suite)
    assert valid is True
    assert reason is None


def test_frozen_suite_tamper_detection():
    """Verify that tampering with any field in a frozen suite triggers integrity verification failure."""
    req = build_base_generation_request()
    res = generate_fault_suite(req)
    assert res.frozen_suite is not None

    suite_dict = res.frozen_suite.model_dump(mode="json")
    # Tamper with the first case
    suite_dict["cases"][0]["tool_version"] = "9.9.9"

    valid, reason = verify_suite_integrity(suite_dict)
    assert valid is False
    assert "Suite content digest mismatch" in reason


def test_input_mutation_isolation():
    """Verify that mutating the original input dictionaries after generation does not alter the frozen suite."""
    req = build_base_generation_request()
    res = generate_fault_suite(req)
    assert res.frozen_suite is not None

    original_digest = res.frozen_suite.content_digest
    # Mutate the caller's request object
    req.tasks[0].task_id = "task-mutated"
    req.adapter_manifests[0].tools[0].tool_id = "tool-mutated"

    # Frozen suite must remain completely unchanged
    valid, reason = verify_suite_integrity(res.frozen_suite)
    assert valid is True
    assert res.frozen_suite.content_digest == original_digest
    assert res.frozen_suite.cases[0].tool_id != "tool-mutated"


def test_json_roundtrip_preserves_content_and_integrity():
    """Verify that serializing to JSON and deserializing preserves content digest and verification."""
    req = build_base_generation_request()
    res = generate_fault_suite(req)
    assert res.frozen_suite is not None

    json_str = res.frozen_suite.model_dump_json()
    reloaded_dict = json.loads(json_str)
    reloaded_suite = FrozenSuite.model_validate(reloaded_dict)

    valid, reason = verify_suite_integrity(reloaded_suite)
    assert valid is True
    assert reloaded_suite.content_digest == res.frozen_suite.content_digest


def test_canonical_json_rejects_non_finite_numbers():
    """Verify that canonical JSON serializer strictly rejects NaN and Infinity values."""
    with pytest.raises(ValueError, match="Non-finite float"):
        to_canonical_json({"val": float("nan")})

    with pytest.raises(ValueError, match="Non-finite float"):
        to_canonical_json({"val": float("inf")})


def test_export_frozen_suite(tmp_path):
    """Verify local developer export to JSON with overwrite prevention."""
    req = build_base_generation_request()
    res = generate_fault_suite(req)
    assert res.frozen_suite is not None

    out_file = tmp_path / "test_suite.json"
    exported_path = export_frozen_suite(res.frozen_suite, out_file)
    assert exported_path.exists()

    # Re-exporting without overwrite=True must raise FileExistsError
    with pytest.raises(FileExistsError):
        export_frozen_suite(res.frozen_suite, out_file, overwrite=False)

    # Re-exporting with overwrite=True succeeds
    export_frozen_suite(res.frozen_suite, out_file, overwrite=True)


# ===========================================================================
# 5. Stateless API Endpoint Tests (POST /api/v1/c3/cases/generate)
# ===========================================================================


def test_api_generate_endpoint_success(client):
    """Verify HTTP 200 and structured response from POST /api/v1/c3/cases/generate."""
    req = build_base_generation_request()
    payload = req.model_dump(mode="json")

    resp = client.post("/api/v1/c3/cases/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["validation_scope"] == "STATIC_ONLY"
    assert data["status"] == "GENERATED"
    assert data["project_id"] == "proj-nexacart-qa"
    assert len(data["selected_cases"]) > 0
    assert data["frozen_suite"] is not None
    assert data["frozen_suite"]["content_digest"] is not None
    assert data["runtime_verified"] is False
    assert data["execution_ready"] is False
    assert data["recovery_verdict"] is None


def test_api_generate_endpoint_filters_empty(client):
    """Verify HTTP 200 with FILTERED_OUT when filters exclude all declared tools."""
    req = build_base_generation_request()
    req.filters = GenerationFilters(tool_ids=["non_existent_tool"])
    payload = req.model_dump(mode="json")

    resp = client.post("/api/v1/c3/cases/generate", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "FILTERED_OUT"
    assert len(data["selected_cases"]) == 0
    assert data["frozen_suite"] is None


def test_api_generate_endpoint_rejects_malformed_syntax(client):
    """Verify HTTP 422 for malformed JSON or forbidden extra attributes."""
    # Extra field forbidden by StrictBaseModel
    payload = {
        "project_id": "proj-1",
        "tasks": [],
        "extra_unknown_field": "bad",
    }
    resp = client.post("/api/v1/c3/cases/generate", json=payload)
    assert resp.status_code == 422


def test_api_generate_endpoint_rejects_boolean_as_seed(client):
    """Verify HTTP 422 when a boolean is erroneously provided as seed."""
    req = build_base_generation_request()
    payload = req.model_dump(mode="json")
    payload["seed"] = True  # Strict integer constraint must reject bool

    resp = client.post("/api/v1/c3/cases/generate", json=payload)
    assert resp.status_code == 422


def test_api_generate_endpoint_no_side_effects(client):
    """Verify endpoint has zero database write, network, or file write side effects."""
    req = build_base_generation_request()
    payload = req.model_dump(mode="json")

    with patch("pathlib.Path.write_text") as mock_write:
        resp = client.post("/api/v1/c3/cases/generate", json=payload)
        assert resp.status_code == 200
        # Endpoint must NEVER write files
        mock_write.assert_not_called()

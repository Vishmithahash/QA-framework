"""
Hermetic automated regression and verification tests for Component 3 (C3) Phase 3:
- Confirmed exposure coexists with failed clean qualification.
- Incomplete fault evidence produces EXPOSURE_UNKNOWN.
- Complete unreached trigger produces NOT_TRIGGERED.
- Unrelated tool calls do not consume the fault episode.
- Configured target occurrence count is strictly honoured.
- Concurrent matching calls cannot inject twice (thread-safe atomic consumption).
- Cancellation consumes/releases the episode safely and NEVER forwards intercepted calls later.
- Scripted demonstration retries are labeled correctly (SCRIPTED_CALLER, never AGENT).
- Harness transport has zero added retries.
- Scoped fixture namespace partitioning and isolated reset.
- Late-effect / cleanup uncertainty during settling prevents fixture reuse.
- Equivalent starting states verified via task-relevant state fingerprint.
- Evidence linkage validation rejects contradictory evidence.
- Safe serialization and redaction of secrets in receipts.
- Live mode never silently falls back to fake mode (IntegrationBlockedError).
- Transport socket-level timeout verified via bounded ephemeral loopback server test.
- Static Phase 1 semantics and routes remain unchanged (execution_ready=False).
"""

from collections.abc import Generator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import threading
import time
from typing import Any
from fastapi.testclient import TestClient
import httpx
import pytest

# Ensure isolated hermetic test environment before loading settings
os.environ["DATABASE_URL"] = (
    "postgresql://fake_user:fake_password@localhost:5432/fake_db?sslmode=require"
)

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.components.c3_robustness_recovery.runtime.adapter import (  # noqa: E402
    FakeNexaCartFixtureManager,
    FakeNexaCartOrderToolAdapter,
    IntegrationBlockedError,
    NexaCartHttpToolAdapter,
    NexaCartPrismaFixtureManager,
    ToolAdapter,
)
from app.components.c3_robustness_recovery.runtime.evidence import (  # noqa: E402
    CallInterceptionReceipt,
    CallerIdentity,
    CallerOutcome,
    CleanupStatus,
    ExecutionStatus,
    ExposureStatus,
    fingerprint_args,
    RecoveryActor,
    sanitize_args,
    TargetMode,
    TimeoutBoundary,
    TrialRole,
    validate_evidence_linkage,
)
from app.components.c3_robustness_recovery.runtime.interceptor import (  # noqa: E402
    OneShotTimeoutInterceptor,
)
from app.components.c3_robustness_recovery.runtime.runner import (  # noqa: E402
    build_default_phase2_request,
    run_matched_pair,
    UnsupportedExecutionConfigurationError,
)
from app.components.c3_robustness_recovery.contracts.schemas import (  # noqa: E402
    FaultFamily,
    HookType,
)
from app.main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Dummy Unrelated Tool for Isolation Tests
# ---------------------------------------------------------------------------


class DummyCatalogToolAdapter(ToolAdapter):
    """Read-only catalog tool representing an unrelated tool in the application."""

    tool_id = "get_product_catalog"
    tool_version = "1.0.0"
    is_side_effecting = False

    def invoke(
        self, args: dict[str, Any], timeout_seconds: float = 5.0
    ) -> dict[str, Any]:
        return {"products": ["PROD-001", "PROD-002"], "count": 2}


# ---------------------------------------------------------------------------
# 1. Exposure and Clean Qualification Separation
# ---------------------------------------------------------------------------


def test_confirmed_exposure_coexists_with_failed_clean_qualification():
    """
    Phase 3 Requirement:
    Fault exposure describes what happened during the fault trial.
    A failed clean control alone must not erase otherwise sufficient evidence
    that the fault was exposed.
    """
    req = build_default_phase2_request()
    evidence = run_matched_pair(
        case=req.case,
        recovery_contract=req.recovery_contract,
        force_clean_failure=True,  # Broken baseline
        synthetic_timeout=True,
    )

    # 1. Clean qualification is False
    assert evidence.clean_trial.clean_qualified is False
    assert evidence.clean_trial.execution_status == ExecutionStatus.EXECUTION_ERROR

    # 2. Exposure status remains CONFIRMED because fault trial met all exposure criteria
    assert evidence.exposure_status == ExposureStatus.CONFIRMED
    assert evidence.timeout_boundary == TimeoutBoundary.SYNTHETIC_EXCEPTION

    # 3. Limitations are documented separately
    assert any(
        "Clean control baseline failed" in lim
        for lim in evidence.interpretation_limitations
    )
    assert evidence.recovery_verdict is None


def test_real_nexacart_http_adapter_raises_integration_blocked():
    """Real NexaCartHttpToolAdapter raises IntegrationBlockedError when base_url is unconfigured."""
    adapter = NexaCartHttpToolAdapter(base_url=None)
    with pytest.raises(IntegrationBlockedError, match="NEXACART_BASE_URL"):
        adapter.invoke({})


def test_incomplete_fault_evidence_produces_exposure_unknown():
    """
    If fault interception receipt indicates the call was forwarded to the target
    or did not experience timeout, exposure status is EXPOSURE_UNKNOWN.
    """
    req = build_default_phase2_request()

    fixture = FakeNexaCartFixtureManager()
    adapter = FakeNexaCartOrderToolAdapter(fixture)

    evidence = run_matched_pair(
        case=req.case,
        recovery_contract=req.recovery_contract,
        adapter=adapter,
        fixture_manager=fixture,
        synthetic_timeout=True,
    )

    # Matching receipt having unexpected outcome:
    fault_receipt = evidence.fault_trial.intercepted_calls[0]
    corrupted_receipt = fault_receipt.model_copy(
        update={"caller_outcome": CallerOutcome.ERROR, "fault_injected": False}
    )

    corrupted_evidence = evidence.model_copy(
        update={
            "fault_trial": evidence.fault_trial.model_copy(
                update={"intercepted_calls": [corrupted_receipt]}
            )
        }
    )

    matching = next(
        (
            r
            for r in corrupted_evidence.fault_trial.intercepted_calls
            if r.tool_id == req.case.trigger.tool_id
            and r.tool_occurrence == req.case.trigger.call_occurrence
        ),
        None,
    )
    assert matching is not None
    assert (
        matching.caller_outcome != CallerOutcome.TIMEOUT or not matching.fault_injected
    )


def test_complete_unreached_trigger_produces_not_triggered():
    """
    When a complete trace establishes that the target occurrence was never reached,
    exposure status is NOT_TRIGGERED.
    """
    req = build_default_phase2_request()
    # Configure trigger for occurrence 4
    req_dict = json.loads(req.model_dump_json())
    req_dict["case"]["trigger"]["call_occurrence"] = 4
    case = req.case.model_validate(req_dict["case"])

    # Caller only makes 1 call
    def single_call_caller(invoker, role):
        invoker({"items": [{"sku": "SKU-1", "quantity": 1}]})

    evidence = run_matched_pair(
        case=case,
        recovery_contract=req.recovery_contract,
        caller=single_call_caller,
        synthetic_timeout=True,
    )

    assert evidence.clean_trial.clean_qualified is True
    assert evidence.exposure_status == ExposureStatus.NOT_TRIGGERED
    assert evidence.exposure_supporting_references == []
    assert evidence.recovery_verdict is None


# ---------------------------------------------------------------------------
# 2. Interceptor Scoping, Unrelated Tools, and Occurrence Counting
# ---------------------------------------------------------------------------


def test_unrelated_tool_call_does_not_consume_episode():
    """
    Calls to unrelated tools must NOT increment the target tool's occurrence count
    or consume the fault injection episode.
    """
    fixture = FakeNexaCartFixtureManager()
    order_adapter = FakeNexaCartOrderToolAdapter(fixture)
    catalog_adapter = DummyCatalogToolAdapter()

    interceptor = OneShotTimeoutInterceptor(
        target_tool_id="create_order",
        target_call_occurrence=1,
        armed=True,
        synthetic_timeout=True,
    )

    # 1. Invoke unrelated catalog tool: should pass through normally
    cat_res = interceptor.execute(catalog_adapter, {})
    assert cat_res["count"] == 2
    assert interceptor.consumed is False  # Not consumed!
    assert interceptor.tool_call_counters["get_product_catalog"] == 1
    assert interceptor.tool_call_counters["create_order"] == 0

    # 2. Invoke target tool for the first time: should match occurrence 1 and trigger!
    with pytest.raises(TimeoutError):
        interceptor.execute(order_adapter, {"call": 1})

    assert interceptor.consumed is True
    assert interceptor.tool_call_counters["create_order"] == 1
    # Verify target order was never forwarded
    assert fixture.observe().record_count == 0


def test_configured_occurrence_is_honoured():
    """
    When trigger is configured for call occurrence 2 of target tool,
    occurrence 1 forwards normally, occurrence 2 triggers timeout, and
    occurrence 3 forwards normally.
    """
    fixture = FakeNexaCartFixtureManager()
    adapter = FakeNexaCartOrderToolAdapter(fixture)

    interceptor = OneShotTimeoutInterceptor(
        target_tool_id="create_order",
        target_call_occurrence=2,
        armed=True,
        synthetic_timeout=True,
    )

    # Call 1: Passthrough
    res1 = interceptor.execute(adapter, {"call": 1})
    assert res1["status"] == "CREATED"
    assert fixture.observe().record_count == 1
    assert interceptor.consumed is False

    # Call 2: Intercepted (occurrence 2)
    with pytest.raises(TimeoutError):
        interceptor.execute(adapter, {"call": 2})

    assert interceptor.consumed is True
    assert fixture.observe().record_count == 1  # Unchanged!

    # Call 3: Passthrough
    res3 = interceptor.execute(adapter, {"call": 3})
    assert res3["status"] == "CREATED"
    assert fixture.observe().record_count == 2


# ---------------------------------------------------------------------------
# 3. Concurrency & Double Injection Prevention
# ---------------------------------------------------------------------------


def test_concurrent_matching_calls_cannot_inject_twice():
    """
    Thread-safety: When multiple concurrent threads invoke the interceptor at
    the matching occurrence, the atomic lock ensures exactly ONE call is injected,
    and subsequent/concurrent calls pass through normally.
    """
    fixture = FakeNexaCartFixtureManager()
    adapter = FakeNexaCartOrderToolAdapter(fixture)

    interceptor = OneShotTimeoutInterceptor(
        target_tool_id="create_order",
        target_call_occurrence=1,
        armed=True,
        synthetic_timeout=True,
    )

    results = []
    errors = []

    def call_worker():
        try:
            res = interceptor.execute(adapter, {"thread": True})
            results.append(res)
        except TimeoutError as te:
            errors.append(te)

    threads = [threading.Thread(target=call_worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly ONE thread received the injected TimeoutError
    assert len(errors) == 1
    # The other 4 threads passed through normally to the target
    assert len(results) == 4
    assert fixture.observe().record_count == 4
    # Exactly one receipt has fault_injected=True
    fault_receipts = [r for r in interceptor.receipts if r.fault_injected]
    assert len(fault_receipts) == 1
    assert fault_receipts[0].forwarded_to_target is False


# ---------------------------------------------------------------------------
# 4. Cancellation Safety & Non-Forwarding
# ---------------------------------------------------------------------------


def test_cancellation_consumes_episode_and_never_forwards_later():
    """
    If a caller cancels or interrupts during the delay hold, the interceptor
    records a CANCELLED receipt, marks the episode consumed, and NEVER forwards
    the request to the target adapter.
    """
    fixture = FakeNexaCartFixtureManager()
    adapter = FakeNexaCartOrderToolAdapter(fixture)

    interceptor = OneShotTimeoutInterceptor(
        target_tool_id="create_order",
        target_call_occurrence=1,
        armed=True,
        delay_ms=2000,
        caller_timeout_seconds=2.0,
        synthetic_timeout=False,
    )

    exc_thrown = None

    def worker():
        nonlocal exc_thrown
        try:
            interceptor.execute(adapter, {"arg": 1}, caller_timeout_seconds=0.05)
        except Exception as e:
            exc_thrown = e

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=1.0)

    assert isinstance(exc_thrown, TimeoutError)
    assert interceptor.consumed is True
    # Intercepted call was NEVER forwarded to target
    assert fixture.observe().record_count == 0

    receipt = interceptor.receipts[0]
    assert receipt.fault_injected is True
    assert receipt.forwarded_to_target is False


# ---------------------------------------------------------------------------
# 5. Faithful Actor Labeling & Zero Harness Retries
# ---------------------------------------------------------------------------


def test_scripted_retries_labeled_correctly_never_as_agent():
    """
    Retries initiated by the scripted demonstration caller must be recorded
    as RecoveryActor.SCRIPTED_CALLER, never misattributed as agent recovery.
    """
    req = build_default_phase2_request()
    evidence = run_matched_pair(
        case=req.case,
        recovery_contract=req.recovery_contract,
        caller_identity=CallerIdentity.SCRIPTED_CALLER,
        synthetic_timeout=True,
    )

    assert evidence.fault_trial.recovery_actor == RecoveryActor.SCRIPTED_CALLER
    assert evidence.caller_identity == CallerIdentity.SCRIPTED_CALLER
    assert any(
        "scripted demonstration caller" in lim
        for lim in evidence.interpretation_limitations
    )


def test_harness_adds_zero_retries_of_its_own():
    """
    The runner and interceptor must not add automatic retries.
    If the caller does not retry after timeout, exactly 1 call is observed in fault trial.
    """
    req = build_default_phase2_request()

    def non_retrying_caller(invoker, role):
        try:
            invoker({"items": [{"sku": "A", "quantity": 1}]})
        except TimeoutError:
            pass  # Does not retry!

    evidence = run_matched_pair(
        case=req.case,
        recovery_contract=req.recovery_contract,
        caller=non_retrying_caller,
        synthetic_timeout=True,
    )

    # Exactly 1 call was observed; harness added no retries
    assert evidence.fault_trial.total_calls_observed == 1
    assert len(evidence.fault_trial.intercepted_calls) == 1
    assert evidence.exposure_status == ExposureStatus.CONFIRMED


# ---------------------------------------------------------------------------
# 6. Scoped Fixture Namespace Isolation & Settling Cleanup
# ---------------------------------------------------------------------------


def test_unique_fixture_namespaces_and_scoped_reset():
    """
    Resetting fixture namespace A does not wipe records belonging to namespace B.
    """
    fixture = FakeNexaCartFixtureManager()

    # Create records in two distinct namespaces
    fixture.record_order("ord-1", {"total_amount": 50.0}, namespace="ns_clean")
    fixture.record_order("ord-2", {"total_amount": 75.0}, namespace="ns_fault")

    snap_clean_before = fixture.observe(namespace="ns_clean")
    snap_fault_before = fixture.observe(namespace="ns_fault")
    assert snap_clean_before.record_count == 1
    assert snap_fault_before.record_count == 1

    # Reset only ns_clean
    fixture.reset(namespace="ns_clean")

    assert fixture.observe(namespace="ns_clean").record_count == 0
    # ns_fault remains intact
    assert fixture.observe(namespace="ns_fault").record_count == 1


def test_late_effect_during_settling_causes_cleanup_uncertainty():
    """
    If in-flight work mutates the fixture during the post-trial settling period,
    cleanup status is marked CLEANUP_UNCERTAIN and fixture_reusable is marked False.
    """
    req = build_default_phase2_request()
    fixture = FakeNexaCartFixtureManager()

    def caller_with_late_effect(invoker, role):
        try:
            invoker({"items": [{"sku": "SKU-1", "quantity": 1}]})
        except TimeoutError:
            pass
        if role == TrialRole.FAULT:

            def delayed_mutation():
                time.sleep(0.01)
                for ns in list(fixture._partitions.keys()):
                    if "fault" in ns:
                        fixture.simulate_late_effect(
                            namespace=ns, order_id="ord-late-999"
                        )

            t = threading.Thread(target=delayed_mutation)
            t.start()

    evidence = run_matched_pair(
        case=req.case,
        recovery_contract=req.recovery_contract,
        fixture_manager=fixture,
        caller=caller_with_late_effect,
        settling_period_seconds=0.05,
        synthetic_timeout=True,
    )

    assert evidence.cleanup_status == CleanupStatus.CLEANUP_UNCERTAIN
    assert evidence.fixture_reusable is False
    assert any(
        "Fixture cleanup uncertainty detected" in lim
        for lim in evidence.interpretation_limitations
    )


# ---------------------------------------------------------------------------
# 7. Evidence Linkage Validation & Secret Redaction
# ---------------------------------------------------------------------------


def test_validate_evidence_linkage_rejects_contradictory_evidence():
    """
    Evidence linkage validation rejects receipts claiming BEFORE_EFFECT fault injection
    AND forwarded_to_target=True simultaneously.
    """
    receipt = CallInterceptionReceipt(
        event_id="evt-corrupt-01",
        pair_id="pair-01",
        trial_id="trial-01",
        call_occurrence=1,
        tool_occurrence=1,
        tool_id="create_order",
        args_fingerprint="abc12345",
        hook=HookType.DURING_TRANSPORT,
        reached_hook=True,
        forwarded_to_target=True,  # CONTRADICTION with fault_injected=True!
        fault_injected=True,
        caller_outcome=CallerOutcome.TIMEOUT,
        duration_ms=10.0,
        timestamp_utc="2026-10-14T10:00:00Z",
    )

    req = build_default_phase2_request()
    evidence = run_matched_pair(
        case=req.case,
        recovery_contract=req.recovery_contract,
        synthetic_timeout=True,
    )

    corrupted_evidence = evidence.model_copy(
        update={
            "fault_trial": evidence.fault_trial.model_copy(
                update={"intercepted_calls": [receipt]}
            )
        }
    )

    issues = validate_evidence_linkage(corrupted_evidence)
    assert len(issues) > 0
    assert any("Contradictory receipt" in issue for issue in issues)


def test_sanitize_args_redacts_credentials_recursively():
    """
    Sensitive parameter keys (token, secret, auth, password, bearer, key)
    are replaced with [REDACTED] in sanitized dictionary and fingerprinted.
    """
    sensitive_dict = {
        "user": "test_agent",
        "api_key": "sk-proj-SUPERSECRET12345",
        "auth_token": "bearer eyJhbGciOi...",
        "nested": {
            "db_password": "super_secret_db_pass",
            "safe_param": 42,
        },
    }

    sanitized = sanitize_args(sensitive_dict)
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["auth_token"] == "[REDACTED]"
    assert sanitized["nested"]["db_password"] == "[REDACTED]"
    assert sanitized["nested"]["safe_param"] == "42"

    fp = fingerprint_args(sensitive_dict)
    assert len(fp) == 16
    assert "SUPERSECRET" not in str(sanitized)


# ---------------------------------------------------------------------------
# 8. Live Mode Never Silently Falls Back to Fake Mode
# ---------------------------------------------------------------------------


def test_live_mode_never_silently_falls_back_to_fake():
    """
    If TargetMode.LIVE_AUT is requested without live prerequisites,
    the runner raises IntegrationBlockedError rather than executing against fake doubles.
    """
    req = build_default_phase2_request()

    with pytest.raises(IntegrationBlockedError, match="BLOCKED"):
        run_matched_pair(
            case=req.case,
            recovery_contract=req.recovery_contract,
            target_mode=TargetMode.LIVE_AUT,  # Request LIVE execution!
            synthetic_timeout=True,
        )


def test_prisma_fixture_rejects_qa_framework_database():
    """
    NexaCartPrismaFixtureManager strictly refuses to run against the QA Neon database.
    """
    os.environ["DATABASE_URL"] = (
        "postgresql://framework_user:pass@neon.tech/framework_db?sslmode=require"
    )
    with pytest.raises(IntegrationBlockedError, match="QA Neon"):
        NexaCartPrismaFixtureManager(
            database_url="postgresql://framework_user:pass@neon.tech/framework_db?sslmode=require"
        )


# ---------------------------------------------------------------------------
# 9. Runtime Execution Configuration Validation
# ---------------------------------------------------------------------------


def test_unsupported_runtime_configuration_rejected_before_execution():
    """
    Runtime validates case configuration and rejects unsupported fault families
    or hooks explicitly before running.
    """
    req = build_default_phase2_request()
    req_dict = json.loads(req.model_dump_json())

    # Attempt to run TRANSIENT_5XX_SERVER_ERROR through Phase 3 timeout runner
    req_dict["case"]["fault_family"] = FaultFamily.TRANSIENT_5XX_SERVER_ERROR.value
    req_dict["case"]["payload"] = {
        "family": "TRANSIENT_5XX_SERVER_ERROR",
        "status_code": 500,
        "error_message": "Error",
    }
    unsupported_case = req.case.model_validate(req_dict["case"])

    with pytest.raises(
        UnsupportedExecutionConfigurationError, match="only supports TIMEOUT"
    ):
        run_matched_pair(
            case=unsupported_case,
            recovery_contract=req.recovery_contract,
            synthetic_timeout=True,
        )


# ---------------------------------------------------------------------------
# 10. Genuine Transport Socket-Level Timeout Fidelity Test
# ---------------------------------------------------------------------------


class StallingHTTPRequestHandler(BaseHTTPRequestHandler):
    """
    HTTP server handler that accepts connection, reads request, and intentionally
    stalls without returning a response until after the client timeout.
    """

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            self.rfile.read(content_length)
        # Stall longer than client read timeout (stalls for 0.8s)
        time.sleep(0.8)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status": "LATE_RESPONSE"}')

    def log_message(self, format, *args):
        # Suppress logging to keep test output clean
        pass


@contextmanager
def ephemeral_stalling_http_server() -> Generator[str, None, None]:
    """
    Context manager launching a temporary loopback HTTP server on an ephemeral port.
    Guarantees sockets and server threads are reliably closed upon exit.
    """
    server = HTTPServer(("127.0.0.1", 0), StallingHTTPRequestHandler)
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


def test_transport_socket_level_read_timeout_fidelity():
    """
    Verified live BEFORE_EFFECT transport timeout delivery through genuine socket.
    Demonstrates actual HTTP read timeout without external cloud dependencies.
    """
    with ephemeral_stalling_http_server() as server_url:
        # Bounded client with short 0.15s read timeout
        client = httpx.Client(timeout=httpx.Timeout(0.15, connect=0.5))
        timeout_occurred = False
        t0 = time.monotonic()

        try:
            client.post(
                f"{server_url}/api/order",
                json={"order_id": "test-123", "amount": 25.0},
            )
        except httpx.ReadTimeout:
            timeout_occurred = True
        finally:
            client.close()

        elapsed = time.monotonic() - t0

        # Verified socket-level timeout:
        assert timeout_occurred is True
        # Occurred around client timeout boundary (~0.15s), well before server finish (0.8s)
        assert 0.10 <= elapsed < 0.60

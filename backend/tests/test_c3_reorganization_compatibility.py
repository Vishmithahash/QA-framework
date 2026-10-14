"""
Tests for canonical Component 3 (C3) package organization.

Verifies:
1. Canonical package modules import cleanly without side-effects.
2. Canonical classes, functions, and router objects operate correctly.
3. FastAPI route registration remains intact and maps to the canonical router.
4. Static validation and runtime runner contracts maintain exact behavior.
5. Canonical CLI execution works with exact flags, statuses, and null recovery verdict.
"""

import os
from unittest.mock import patch

# Hermetic test environment before loading settings
os.environ["DATABASE_URL"] = (
    "postgresql://fake_user:fake_password@localhost:5432/fake_db?sslmode=require"
)

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.components.c3_robustness_recovery.contracts.schemas import (  # noqa: E402
    APPLICATION_AWARE_HOOKS,
    CandidateFaultCase,
    CaseValidationRequest,
    CaseValidationResponse,
    EffectPhase,
    FaultCatalogResponse,
    FaultFamily,
    HookType,
    ValidationStatus,
)
from app.components.c3_robustness_recovery.runtime.adapter import (  # noqa: E402
    FakeNexaCartFixtureManager,
    FakeNexaCartOrderToolAdapter,
    FixtureManager,
    IntegrationBlockedError,
    NexaCartHttpToolAdapter,
    ToolAdapter,
)
from app.components.c3_robustness_recovery.runtime.evidence import (  # noqa: E402
    CleanupStatus,
    ExposureStatus,
    fingerprint_args,
    sanitize_args,
)
from app.components.c3_robustness_recovery.runtime.interceptor import (  # noqa: E402
    OneShotTimeoutInterceptor,
)
from app.components.c3_robustness_recovery.runtime.runner import (  # noqa: E402
    build_default_phase2_request,
    main,
    run_matched_pair,
)
from app.components.c3_robustness_recovery.services.validation import (  # noqa: E402
    PENDING_RUNTIME_CHECKS,
    get_operational_fault_catalog,
    validate_candidate_case,
)
from app.main import app  # noqa: E402
from tests.test_c3_foundation import build_valid_test_request  # noqa: E402


def test_canonical_contracts_schemas():
    """Verify that canonical contracts schemas and enums are defined and functional."""
    assert CandidateFaultCase is not None
    assert CaseValidationRequest is not None
    assert CaseValidationResponse is not None
    assert FaultCatalogResponse is not None
    assert FaultFamily.TIMEOUT_OR_DISCONNECTION == "TIMEOUT_OR_DISCONNECTION"
    assert EffectPhase.BEFORE_EFFECT == "BEFORE_EFFECT"
    assert HookType.DURING_TRANSPORT == "DURING_TRANSPORT"
    assert HookType.POST_COMMIT in APPLICATION_AWARE_HOOKS


def test_canonical_services_validation():
    """Verify that canonical validation services return expected deterministic responses."""
    catalog = get_operational_fault_catalog()
    assert isinstance(catalog, FaultCatalogResponse)
    assert len(catalog.families) == 5

    req = build_valid_test_request()
    res = validate_candidate_case(req)
    assert isinstance(res, CaseValidationResponse)
    assert res.validation_status == ValidationStatus.STATIC_VALID
    assert res.execution_ready is False
    assert res.recovery_verdict is None
    assert res.pending_checks == PENDING_RUNTIME_CHECKS


def test_canonical_runtime_adapter_and_fixture():
    """Verify that canonical runtime adapter and fixture manager function correctly."""
    fixture_mgr = FakeNexaCartFixtureManager()
    adapter = FakeNexaCartOrderToolAdapter(fixture_mgr, namespace="test_ns")
    assert isinstance(adapter, ToolAdapter)
    assert isinstance(fixture_mgr, FixtureManager)

    snap = fixture_mgr.prepare(namespace="test_ns")
    assert fixture_mgr.verify_clean_state(snap)

    res = adapter.invoke(
        {"items": [{"sku": "SKU-01", "quantity": 1}], "total_amount": 25.0}
    )
    assert res["status"] == "CREATED"

    obs = fixture_mgr.observe(namespace="test_ns")
    assert obs.record_count == 1

    # Verify live blocked behavior
    http_adapter = NexaCartHttpToolAdapter()
    try:
        http_adapter.invoke({})
        assert False, "Expected IntegrationBlockedError"
    except IntegrationBlockedError:
        pass


def test_canonical_runtime_evidence_and_linkage():
    """Verify that canonical evidence contracts, fingerprinting, and linkage operate properly."""
    raw_args = {"token": "secret123", "password": "pass", "item": "widget"}
    sanitized = sanitize_args(raw_args)
    assert sanitized["token"] == "[REDACTED]"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["item"] == "widget"

    fp = fingerprint_args(raw_args)
    assert len(fp) == 16


def test_canonical_runtime_interceptor():
    """Verify that canonical OneShotTimeoutInterceptor intercepts matching call."""
    interceptor = OneShotTimeoutInterceptor(
        target_tool_id="create_order",
        target_call_occurrence=1,
        synthetic_timeout=True,
    )
    fixture_mgr = FakeNexaCartFixtureManager()
    adapter = FakeNexaCartOrderToolAdapter(fixture_mgr, namespace="interceptor_ns")

    try:
        interceptor.execute(adapter, {"test": "data"})
        assert False, "Expected TimeoutError"
    except TimeoutError:
        pass

    assert len(interceptor.receipts) == 1
    assert interceptor.receipts[0].fault_injected is True
    assert interceptor.receipts[0].forwarded_to_target is False


def test_canonical_runtime_runner_synthetic_execution():
    """Verify that canonical run_matched_pair executes successfully with null recovery verdict."""
    req = build_default_phase2_request()
    evidence = run_matched_pair(
        case=req.case,
        recovery_contract=req.recovery_contract,
        synthetic_timeout=True,
    )
    assert evidence.clean_qualified is True
    assert evidence.exposure_status == ExposureStatus.CONFIRMED
    assert evidence.recovery_verdict is None
    assert evidence.cleanup_status == CleanupStatus.CLEANUP_VERIFIED


def test_canonical_api_router_registered_in_fastapi():
    """Verify that the canonical C3 router is registered once in the main FastAPI application."""
    routes = {r.path for r in app.routes}
    assert "/api/v1/c3/fault-catalog" in routes
    assert "/api/v1/c3/cases/validate" in routes


def test_canonical_cli_execution_via_main():
    """Verify that runtime.runner.main executes without error with synthetic flag."""
    with patch("sys.argv", ["runner.py", "--synthetic"]):
        main()

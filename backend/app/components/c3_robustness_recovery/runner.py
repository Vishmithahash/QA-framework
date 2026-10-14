"""
Matched-pair execution runner and local CLI for Component 3 (C3) Phase 3:
Robustness and Failure Recovery Testing.

Coordinates:
- Configuration freezing across matched clean and fault trials.
- Explicit validation of runtime capability support before execution.
- Scoped fixture namespace partitioning, reset, and observation.
- Clean control trial execution (injection disarmed).
- Fault trial execution (one-shot BEFORE_EFFECT timeout episode armed).
- Decoupled classification of execution status, clean qualification, and exposure status.
  (A failed clean control does not erase confirmed fault exposure).
- Post-trial settling observation to verify cleanup and detect late effects.
- Faithful recovery actor and caller identity labeling.
- Safe local evidence artifact export without durable application database writes.
- Recovery verdict strictly null throughout Phase 3 (no recovery scoring).
"""

import argparse
from collections.abc import Callable
import json
from pathlib import Path
import time
from typing import Any
from uuid import uuid4
from app.components.c3_robustness_recovery.adapter import (
    FakeNexaCartFixtureManager,
    FakeNexaCartOrderToolAdapter,
    FixtureManager,
    IntegrationBlockedError,
    NexaCartHttpToolAdapter,
    NexaCartPrismaFixtureManager,
    ToolAdapter,
)
from app.components.c3_robustness_recovery.evidence import (
    CallerIdentity,
    CallerOutcome,
    CleanupStatus,
    current_utc_iso,
    ExecutionStatus,
    ExposureStatus,
    MatchedPairEvidence,
    RecoveryActor,
    save_evidence_artifact,
    TargetMode,
    TimeoutBoundary,
    TrialEvidence,
    TrialRole,
    validate_evidence_linkage,
)
from app.components.c3_robustness_recovery.interceptor import (
    OneShotTimeoutInterceptor,
)
from app.components.c3_robustness_recovery.schemas import (
    CandidateFaultCase,
    CaseValidationRequest,
    EffectPhase,
    FaultFamily,
    HookType,
    RecoveryContract,
    ReleaseRuleMode,
    TimeoutMode,
    TimeoutPayload,
)


class UnsupportedExecutionConfigurationError(ValueError):
    """Raised when declared case requires runtime capabilities not supported by C3 Phase 3."""


def validate_runtime_case_support(case: CandidateFaultCase) -> None:
    """
    Validate that the candidate case configuration is genuinely supported by the Phase 3 runtime.
    Rejects unsupported execution configurations before execution rather than silently misbehaving.
    """
    if case.fault_family != FaultFamily.TIMEOUT_OR_DISCONNECTION:
        raise UnsupportedExecutionConfigurationError(
            f"Runtime only supports TIMEOUT_OR_DISCONNECTION in Phase 3; got {case.fault_family}."
        )
    if case.effect_phase != EffectPhase.BEFORE_EFFECT:
        raise UnsupportedExecutionConfigurationError(
            f"Runtime only supports BEFORE_EFFECT injection in Phase 3; got {case.effect_phase}."
        )
    if case.release_rule.mode not in (
        ReleaseRuleMode.SINGLE_CALL,
        ReleaseRuleMode.COUNT_BASED,
    ):
        raise UnsupportedExecutionConfigurationError(
            f"Runtime does not support release rule mode {case.release_rule.mode} in Phase 3."
        )
    if (
        case.release_rule.mode == ReleaseRuleMode.COUNT_BASED
        and case.release_rule.max_fault_occurrences != 1
    ):
        raise UnsupportedExecutionConfigurationError(
            "Runtime only supports one-shot single-occurrence fault release in Phase 3."
        )
    if case.trigger.hook not in (
        HookType.DURING_TRANSPORT,
        HookType.PRE_TOOL_INVOCATION,
    ):
        raise UnsupportedExecutionConfigurationError(
            f"Runtime hook {case.trigger.hook} is not supported for transport timeouts in Phase 3."
        )


def default_scripted_caller(
    invoker: Callable[[dict[str, Any]], dict[str, Any]],
    trial_role: TrialRole,
) -> dict[str, Any]:
    """
    Standard scripted demonstration caller.

    Behavior:
    - Attempt 1: Invokes target tool.
    - If TimeoutError occurs:
      - Observes timeout.
      - Initiates one scripted demonstration retry (Attempt 2) to verify post-fault passthrough.
    - Explicitly labeled as scripted caller retry; NEVER labeled as agent decision.
    """
    first_call_args = {
        "items": [{"sku": "NEXA-PROD-101", "quantity": 1}],
        "total_amount": 79.99,
        "idempotency_key": f"idem-{uuid4().hex[:8]}",
    }

    try:
        res1 = invoker(first_call_args)
        return {
            "attempts": 1,
            "final_status": "SUCCESS",
            "recovery_actor": RecoveryActor.SCRIPTED_CALLER,
            "result": res1,
        }
    except TimeoutError:
        # Caller observed timeout
        # Scripted demonstration caller executes a retry
        retry_args = {
            "items": [{"sku": "NEXA-PROD-101", "quantity": 1}],
            "total_amount": 79.99,
            "idempotency_key": first_call_args["idempotency_key"],
            "is_retry": True,
        }
        try:
            res2 = invoker(retry_args)
            return {
                "attempts": 2,
                "first_call_timed_out": True,
                "final_status": "RECOVERED_AFTER_RETRY",
                "recovery_actor": RecoveryActor.SCRIPTED_CALLER,
                "result": res2,
            }
        except Exception as exc:
            return {
                "attempts": 2,
                "first_call_timed_out": True,
                "final_status": "FAILED_ON_RETRY",
                "recovery_actor": RecoveryActor.SCRIPTED_CALLER,
                "error": str(exc),
            }


def run_matched_pair(
    case: CandidateFaultCase,
    recovery_contract: RecoveryContract,
    adapter: ToolAdapter | None = None,
    fixture_manager: FixtureManager | None = None,
    caller: (
        Callable[[Callable[[dict[str, Any]], dict[str, Any]], TrialRole], Any] | None
    ) = None,
    caller_identity: CallerIdentity = CallerIdentity.SCRIPTED_CALLER,
    target_mode: TargetMode = TargetMode.FAKE_ADAPTER,
    timeout_boundary: TimeoutBoundary = TimeoutBoundary.TOOL_CALL_DEADLINE,
    timeout_boundary_subtype: str | None = None,
    output_dir: Path | str | None = None,
    synthetic_timeout: bool = False,
    caller_timeout_seconds: float = 2.0,
    force_clean_failure: bool = False,
    settling_period_seconds: float = 0.05,
) -> MatchedPairEvidence:
    """
    Execute a matched clean/fault pair for a declared candidate case.

    Guarantees:
    1. Rejects unsupported execution configurations explicitly before running.
    2. Enforces unique fixture namespaces for each run/trial rather than one fixed global store.
    3. Retains failed clean controls without rerun-until-pass; decoupled exposure status is NOT
       erased by clean baseline failure.
    4. Never silently falls back from live target mode to fake mode.
    5. Faithfully records caller identity and recovery actors.
    6. Verifies fixture equivalence and post-trial settling/cleanup status.
    7. Keeps recovery_verdict strictly null (None).
    """
    # 0. Runtime capability validation
    validate_runtime_case_support(case)

    # 1. Enforce live target mode restrictions (no silent fallback)
    if target_mode == TargetMode.LIVE_AUT:
        if adapter is None:
            adapter = NexaCartHttpToolAdapter()
        if fixture_manager is None:
            fixture_manager = NexaCartPrismaFixtureManager()

    pair_id = f"pair-{uuid4().hex[:8]}"
    project_id = case.project_id
    case_id = case.case_id
    run_id = f"run-{uuid4().hex[:8]}"

    # Unique fixture partition namespaces
    clean_namespace = f"{case.fixture_id}_{pair_id}_clean"
    fault_namespace = f"{case.fixture_id}_{pair_id}_fault"

    # Default in-memory isolated test target
    if fixture_manager is None:
        fixture_manager = FakeNexaCartFixtureManager(
            fixture_id=case.fixture_id,
            fixture_version=case.fixture_version,
        )
    if adapter is None:
        if isinstance(fixture_manager, FakeNexaCartFixtureManager):
            adapter = FakeNexaCartOrderToolAdapter(
                fixture_manager, namespace=clean_namespace
            )
        else:
            raise ValueError("Adapter must be provided for custom fixture manager.")

    active_caller = caller or default_scripted_caller

    # Faithful recovery actor assignment
    if caller is not None and caller_identity == CallerIdentity.ACTUAL_TESTED_AGENT:
        default_recovery_actor = RecoveryActor.AGENT
    elif caller_identity == CallerIdentity.SCRIPTED_CALLER:
        default_recovery_actor = RecoveryActor.SCRIPTED_CALLER
    else:
        default_recovery_actor = RecoveryActor.UNKNOWN

    effective_timeout_boundary = (
        TimeoutBoundary.SYNTHETIC_EXCEPTION if synthetic_timeout else timeout_boundary
    )

    # 2. Freeze immutable configuration snapshot across both trials
    case_snapshot = case.model_dump()
    recovery_contract_snapshot = recovery_contract.model_dump()
    adapter_version_snapshot = {adapter.tool_id: adapter.tool_version}
    environment_snapshot = {
        "fixture_id": fixture_manager.fixture_id,
        "fixture_version": fixture_manager.fixture_version,
        "target_mode": target_mode.value,
        "caller_identity": caller_identity.value,
        "caller_timeout_seconds": caller_timeout_seconds,
        "timeout_boundary": effective_timeout_boundary.value,
        "synthetic_timeout": synthetic_timeout,
    }

    # -----------------------------------------------------------------------
    # 3. Clean Control Trial
    # -----------------------------------------------------------------------
    clean_trial_id = f"trial-clean-{uuid4().hex[:8]}"
    if isinstance(adapter, FakeNexaCartOrderToolAdapter):
        adapter.set_namespace(clean_namespace)

    clean_initial_fixture = fixture_manager.reset(namespace=clean_namespace)

    clean_interceptor = OneShotTimeoutInterceptor(
        target_tool_id=case.trigger.tool_id,
        target_call_occurrence=case.trigger.call_occurrence,
        hook=case.trigger.hook,
        armed=False,  # Disarmed for clean control
        synthetic_timeout=synthetic_timeout,
        caller_timeout_seconds=caller_timeout_seconds,
        pair_id=pair_id,
        trial_id=clean_trial_id,
        timeout_boundary=effective_timeout_boundary,
    )

    t0 = time.monotonic()
    clean_exec_status = ExecutionStatus.COMPLETED
    clean_error_msg = None

    if force_clean_failure:
        # Explicit test override to verify retention of failed clean controls
        clean_exec_status = ExecutionStatus.EXECUTION_ERROR
        clean_error_msg = "Simulated forced clean baseline failure"
    else:
        try:
            active_caller(
                lambda args: clean_interceptor.execute(
                    adapter, args, caller_timeout_seconds=caller_timeout_seconds
                ),
                TrialRole.CLEAN,
            )
        except Exception as exc:
            clean_exec_status = ExecutionStatus.EXECUTION_ERROR
            clean_error_msg = str(exc)

    clean_duration = time.monotonic() - t0

    # Close trial in-flight window
    clean_interceptor.deactivate()
    if settling_period_seconds > 0:
        time.sleep(settling_period_seconds)

    clean_final_fixture = fixture_manager.observe(namespace=clean_namespace)

    # Clean qualification requires clean completion and verified mutation
    clean_qualified = (
        clean_exec_status == ExecutionStatus.COMPLETED
        and clean_final_fixture.record_count > clean_initial_fixture.record_count
    )

    clean_evidence = TrialEvidence(
        trial_id=clean_trial_id,
        pair_id=pair_id,
        trial_role=TrialRole.CLEAN,
        execution_status=clean_exec_status,
        clean_qualified=clean_qualified,
        initial_fixture=clean_initial_fixture,
        final_fixture=clean_final_fixture,
        settling_fixture=clean_final_fixture,
        intercepted_calls=clean_interceptor.receipts,
        total_calls_observed=clean_interceptor.total_call_counter,
        duration_seconds=clean_duration,
        recovery_actor=default_recovery_actor,
        cleanup_status=CleanupStatus.CLEANUP_VERIFIED,
        error_message=clean_error_msg,
    )

    # -----------------------------------------------------------------------
    # 4. Fault Trial
    # -----------------------------------------------------------------------
    fault_trial_id = f"trial-fault-{uuid4().hex[:8]}"
    if isinstance(adapter, FakeNexaCartOrderToolAdapter):
        adapter.set_namespace(fault_namespace)

    fault_initial_fixture = fixture_manager.reset(namespace=fault_namespace)

    # Verify equivalent logical starting states across trials
    fixture_equivalence = fixture_manager.verify_equivalence(
        clean_initial_fixture, fault_initial_fixture
    )

    delay_ms = (
        case.payload.delay_ms if isinstance(case.payload, TimeoutPayload) else 5000
    )
    mode = (
        case.payload.mode
        if isinstance(case.payload, TimeoutPayload)
        else TimeoutMode.CONNECTION_TIMEOUT
    )

    fault_interceptor = OneShotTimeoutInterceptor(
        target_tool_id=case.trigger.tool_id,
        target_call_occurrence=case.trigger.call_occurrence,
        hook=case.trigger.hook,
        timeout_mode=mode,
        delay_ms=delay_ms,
        caller_timeout_seconds=caller_timeout_seconds,
        armed=True,
        synthetic_timeout=synthetic_timeout,
        pair_id=pair_id,
        trial_id=fault_trial_id,
        timeout_boundary=effective_timeout_boundary,
    )

    t0 = time.monotonic()
    fault_exec_status = ExecutionStatus.COMPLETED
    fault_error_msg = None

    try:
        active_caller(
            lambda args: fault_interceptor.execute(
                adapter, args, caller_timeout_seconds=caller_timeout_seconds
            ),
            TrialRole.FAULT,
        )
    except Exception as exc:
        fault_exec_status = ExecutionStatus.EXECUTION_ERROR
        fault_error_msg = str(exc)

    fault_duration = time.monotonic() - t0

    # Stop accepting new calls and observe post-trial settling
    fault_interceptor.deactivate()
    fault_final_fixture = fixture_manager.observe(namespace=fault_namespace)

    if settling_period_seconds > 0:
        time.sleep(settling_period_seconds)

    fault_settling_fixture = fixture_manager.observe(namespace=fault_namespace)

    # Detect unexpected late-arriving side effects during settling period
    late_effects_detected = (
        fault_final_fixture.state_fingerprint
        != fault_settling_fixture.state_fingerprint
    )

    if late_effects_detected:
        cleanup_status = CleanupStatus.CLEANUP_UNCERTAIN
        fixture_reusable = False
    else:
        cleanup_status = CleanupStatus.CLEANUP_VERIFIED
        fixture_reusable = True

    fault_evidence = TrialEvidence(
        trial_id=fault_trial_id,
        pair_id=pair_id,
        trial_role=TrialRole.FAULT,
        execution_status=fault_exec_status,
        clean_qualified=None,
        initial_fixture=fault_initial_fixture,
        final_fixture=fault_final_fixture,
        settling_fixture=fault_settling_fixture,
        intercepted_calls=fault_interceptor.receipts,
        total_calls_observed=fault_interceptor.total_call_counter,
        duration_seconds=fault_duration,
        recovery_actor=default_recovery_actor,
        cleanup_status=cleanup_status,
        error_message=fault_error_msg,
    )

    # -----------------------------------------------------------------------
    # 5. Decoupled Exposure Classification
    # -----------------------------------------------------------------------
    # Rule 1: A failed clean control alone must not erase otherwise sufficient
    # evidence that the fault was exposed. Exposure describes what occurred in
    # the fault trial.
    matching_receipt = next(
        (
            r
            for r in fault_interceptor.receipts
            if r.tool_id == case.trigger.tool_id
            and r.tool_occurrence == case.trigger.call_occurrence
        ),
        None,
    )

    supporting_refs: list[str] = []
    if matching_receipt is None:
        exposure_status = ExposureStatus.NOT_TRIGGERED
    else:
        supporting_refs.append(matching_receipt.event_id)
        if (
            matching_receipt.reached_hook
            and (not matching_receipt.forwarded_to_target)
            and matching_receipt.fault_injected
            and matching_receipt.caller_outcome
            in (CallerOutcome.TIMEOUT, CallerOutcome.CANCELLED)
        ):
            exposure_status = ExposureStatus.CONFIRMED
        else:
            exposure_status = ExposureStatus.EXPOSURE_UNKNOWN

    # -----------------------------------------------------------------------
    # 6. Explicit Interpretation Limitations
    # -----------------------------------------------------------------------
    interpretation_limitations: list[str] = []
    if not clean_qualified:
        interpretation_limitations.append(
            "Clean control baseline failed or did not satisfy declared qualification requirements; "
            "recovery evaluation cannot be interpreted validly despite confirmed fault exposure."
        )
    if not fixture_equivalence:
        interpretation_limitations.append(
            "Clean and fault initial fixture states were not equivalent; comparability is compromised."
        )
    if cleanup_status != CleanupStatus.CLEANUP_VERIFIED:
        interpretation_limitations.append(
            "Fixture cleanup uncertainty detected: late in-flight state mutations observed during settling. "
            "Fixture partition marked unavailable for reuse."
        )
    if caller_identity == CallerIdentity.SCRIPTED_CALLER:
        interpretation_limitations.append(
            "Trial executed with scripted demonstration caller; retries represent demonstration flow, "
            "not autonomous LLM agent decisions."
        )
    if target_mode == TargetMode.FAKE_ADAPTER:
        interpretation_limitations.append(
            "Target is an isolated in-memory test double; real NexaCart integration remains blocked."
        )

    # -----------------------------------------------------------------------
    # 7. Assemble and Validate Versioned Evidence Record
    # -----------------------------------------------------------------------
    matched_evidence = MatchedPairEvidence(
        schema_version="1.1.0",
        project_id=project_id,
        case_id=case_id,
        pair_id=pair_id,
        run_id=run_id,
        timestamp_utc=current_utc_iso(),
        target_mode=target_mode,
        caller_identity=caller_identity,
        timeout_boundary=effective_timeout_boundary,
        timeout_boundary_subtype=timeout_boundary_subtype,
        case_snapshot=case_snapshot,
        recovery_contract_snapshot=recovery_contract_snapshot,
        adapter_version_snapshot=adapter_version_snapshot,
        environment_snapshot=environment_snapshot,
        clean_trial=clean_evidence,
        fault_trial=fault_evidence,
        clean_qualified=clean_qualified,
        exposure_status=exposure_status,
        exposure_supporting_references=supporting_refs,
        interpretation_limitations=interpretation_limitations,
        fixture_equivalence=fixture_equivalence,
        cleanup_status=cleanup_status,
        fixture_reusable=fixture_reusable,
        recovery_verdict=None,  # Strictly null in Phase 3
        is_harness_demonstration=True,
        target_tool=adapter.tool_id,
        notes=[
            "Phase 3 hardened paired-trial execution.",
            "Exposure status is evaluated strictly on fault trial receipts, decoupled from clean qualification.",
            "Recovery verdict is strictly null; final recovery scoring is deferred.",
        ],
    )

    # Validate internal event linkage across trials and receipts
    linkage_issues = validate_evidence_linkage(matched_evidence)
    if linkage_issues:
        raise ValueError(
            f"Evidence linkage validation failed: {'; '.join(linkage_issues)}"
        )

    if output_dir:
        save_evidence_artifact(matched_evidence, output_dir)

    return matched_evidence


def build_default_phase2_request() -> CaseValidationRequest:
    """Helper to build a valid candidate case request for the local runner."""
    from tests.test_c3_foundation import build_valid_test_request

    req = build_valid_test_request()
    req_dict = json.loads(req.model_dump_json())
    req_dict["case"]["tool_id"] = "create_order"
    req_dict["case"]["trigger"]["tool_id"] = "create_order"
    req_dict["case"]["trigger"]["call_occurrence"] = 1
    req_dict["case"]["trigger"]["hook"] = HookType.DURING_TRANSPORT.value
    req_dict["adapter_manifest"]["tools"] = [
        {
            "tool_id": "create_order",
            "tool_version": "1.0.0",
            "is_side_effecting": True,
        }
    ]
    req_dict["adapter_manifest"]["capabilities"] = [
        {
            "fault_family": "TIMEOUT_OR_DISCONNECTION",
            "effect_phase": "BEFORE_EFFECT",
            "hook": "DURING_TRANSPORT",
            "observation_method": "obs_network_trace",
            "allowed_modes": ["CONNECTION_TIMEOUT", "READ_TIMEOUT"],
            "min_delay_ms": 100,
            "max_delay_ms": 10000,
            "supported_release_modes": ["SINGLE_CALL"],
        }
    ]
    return CaseValidationRequest.model_validate(req_dict)


def main() -> None:
    """CLI developer runner for local matched pair execution demonstration."""
    parser = argparse.ArgumentParser(
        description="Run C3 Phase 3 matched clean/fault trial pair demonstration."
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./evidence_output",
        help="Local directory path to save versioned JSON evidence artifacts.",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Use fast synthetic timeout for immediate execution.",
    )
    parser.add_argument(
        "--caller-timeout",
        type=float,
        default=0.5,
        help="Caller timeout boundary in seconds (default: 0.5s).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Attempt live target execution (fails if live target prerequisites are missing).",
    )

    args = parser.parse_args()

    print("=== C3 Phase 3: Hardened Matched Clean/Fault Trial Runner ===")
    req = build_default_phase2_request()
    print(f"Target Tool:    {req.case.tool_id}")
    print(f"Fault Family:   {req.case.fault_family}")
    print(f"Effect Phase:   {req.case.effect_phase}")
    print(f"Target Mode:    {'LIVE_AUT' if args.live else 'FAKE_ADAPTER'}")

    target_mode = TargetMode.LIVE_AUT if args.live else TargetMode.FAKE_ADAPTER

    try:
        evidence = run_matched_pair(
            case=req.case,
            recovery_contract=req.recovery_contract,
            target_mode=target_mode,
            output_dir=args.output_dir,
            synthetic_timeout=args.synthetic,
            caller_timeout_seconds=args.caller_timeout,
        )
    except IntegrationBlockedError as ibe:
        print(f"\n[BLOCKED] {ibe}")
        return

    print("\n=== Matched Pair Execution Complete ===")
    print(f"Pair ID:          {evidence.pair_id}")
    print(f"Clean Qualified:  {evidence.clean_trial.clean_qualified}")
    print(f"Exposure Status:  {evidence.exposure_status.value}")
    print(
        f"Recovery Verdict: {evidence.recovery_verdict} (Intentionally null in Phase 3)"
    )
    print(f"Cleanup Status:   {evidence.cleanup_status.value}")
    if evidence.interpretation_limitations:
        print(f"Limitations:      {'; '.join(evidence.interpretation_limitations)}")
    print(f"Evidence Saved:   {args.output_dir}/matched_pair_{evidence.pair_id}.json")


if __name__ == "__main__":
    main()

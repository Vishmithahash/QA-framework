"""
Matched-pair execution runner and local CLI for Component 3 (C3) Phase 2:
Robustness and Failure Recovery Testing.

Coordinates:
- Configuration freezing across matched clean and fault trials.
- Isolated fixture preparation, reset, and observation.
- Clean control trial execution (injection disarmed).
- Fault trial execution (one-shot BEFORE_EFFECT timeout episode armed).
- Separate classification of execution status, clean qualification, and exposure.
- Safe local evidence artifact export without durable application database writes.
- Recovery verdict strictly null (no recovery scoring in Phase 2).
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
    ToolAdapter,
)
from app.components.c3_robustness_recovery.evidence import (
    CallerOutcome,
    current_utc_iso,
    ExecutionStatus,
    ExposureStatus,
    MatchedPairEvidence,
    RecoveryActor,
    save_evidence_artifact,
    TrialEvidence,
    TrialRole,
)
from app.components.c3_robustness_recovery.interceptor import (
    OneShotTimeoutInterceptor,
)
from app.components.c3_robustness_recovery.schemas import (
    CandidateFaultCase,
    CaseValidationRequest,
    HookType,
    RecoveryContract,
    TimeoutMode,
    TimeoutPayload,
)


def default_scripted_caller(
    invoker: Callable[[dict[str, Any]], dict[str, Any]],
    trial_role: TrialRole,
) -> dict[str, Any]:
    """
    Standard scripted caller demonstrating tool invocation and timeout reaction.

    Behavior:
    - Attempt 1: Invokes target tool.
    - If TimeoutError occurs:
      - Observes timeout.
      - Decides on one recovery retry (Attempt 2) to demonstrate post-fault passthrough.
    - Does NOT represent scored LLM recovery; explicitly labeled as harness demonstration.
    """
    first_call_args = {
        "items": [{"sku": "NEXA-PROD-101", "quantity": 1}],
        "total_amount": 79.99,
        "idempotency_key": f"idem-{uuid4().hex[:8]}",
    }

    try:
        res1 = invoker(first_call_args)
        return {"attempts": 1, "final_status": "SUCCESS", "result": res1}
    except TimeoutError:
        # Caller observed timeout
        # Scripted caller initiates a retry attempt
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
                "result": res2,
            }
        except Exception as exc:
            return {
                "attempts": 2,
                "first_call_timed_out": True,
                "final_status": "FAILED_ON_RETRY",
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
    output_dir: Path | str | None = None,
    synthetic_timeout: bool = False,
    caller_timeout_seconds: float = 2.0,
    force_clean_failure: bool = False,
) -> MatchedPairEvidence:
    """
    Execute a matched clean/fault pair for a declared candidate case.

    Steps:
    1. Freeze immutable configuration snapshots.
    2. Clean Control:
       - Reset fixture and observe initial state.
       - Execute with fault interceptor disarmed.
       - Observe final fixture state and qualify clean control.
       - Never rerun failed clean controls.
    3. Fault Trial:
       - Reset fixture and verify equivalent initial state.
       - Execute with one-shot BEFORE_EFFECT timeout interceptor armed.
       - Observe final fixture state.
    4. Correlate receipts and classify exposure (CONFIRMED, NOT_TRIGGERED, EXPOSURE_UNKNOWN).
    5. Ensure recovery_verdict is null.
    6. Persist local evidence artifact if output_dir provided.
    """
    pair_id = f"pair-{uuid4().hex[:8]}"
    project_id = case.project_id
    case_id = case.case_id
    run_id = f"run-{uuid4().hex[:8]}"

    # Default in-memory isolated test target
    if fixture_manager is None:
        fixture_manager = FakeNexaCartFixtureManager(
            fixture_id=case.fixture_id,
            fixture_version=case.fixture_version,
        )
    if adapter is None:
        if isinstance(fixture_manager, FakeNexaCartFixtureManager):
            adapter = FakeNexaCartOrderToolAdapter(fixture_manager)
        else:
            raise ValueError("Adapter must be provided for custom fixture manager.")

    active_caller = caller or default_scripted_caller

    # 1. Freeze configuration snapshot
    case_snapshot = case.model_dump()
    recovery_contract_snapshot = recovery_contract.model_dump()
    adapter_version_snapshot = {adapter.tool_id: adapter.tool_version}
    environment_snapshot = {
        "fixture_id": fixture_manager.fixture_id,
        "fixture_version": fixture_manager.fixture_version,
        "caller_timeout_seconds": caller_timeout_seconds,
        "synthetic_timeout": synthetic_timeout,
    }

    # -----------------------------------------------------------------------
    # 2. Clean Control Trial
    # -----------------------------------------------------------------------
    clean_trial_id = f"trial-clean-{uuid4().hex[:8]}"
    clean_initial_fixture = fixture_manager.reset()

    clean_interceptor = OneShotTimeoutInterceptor(
        target_tool_id=case.trigger.tool_id,
        target_call_occurrence=case.trigger.call_occurrence,
        hook=case.trigger.hook,
        armed=False,  # Disarmed for clean control
        synthetic_timeout=synthetic_timeout,
        caller_timeout_seconds=caller_timeout_seconds,
    )

    t0 = time.monotonic()
    clean_exec_status = ExecutionStatus.COMPLETED
    clean_error_msg = None

    if force_clean_failure:
        # For testing retention of failed clean controls
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
    clean_final_fixture = fixture_manager.observe()

    # Clean qualification: clean control must complete without error and perform intended mutation
    clean_qualified = (
        clean_exec_status == ExecutionStatus.COMPLETED
        and clean_final_fixture.record_count > clean_initial_fixture.record_count
    )

    clean_evidence = TrialEvidence(
        trial_id=clean_trial_id,
        trial_role=TrialRole.CLEAN,
        execution_status=clean_exec_status,
        clean_qualified=clean_qualified,
        initial_fixture=clean_initial_fixture,
        final_fixture=clean_final_fixture,
        intercepted_calls=clean_interceptor.receipts,
        total_calls_observed=clean_interceptor.call_counter,
        duration_seconds=clean_duration,
        recovery_actor=RecoveryActor.UNKNOWN,
        error_message=clean_error_msg,
    )

    # -----------------------------------------------------------------------
    # 3. Fault Trial
    # -----------------------------------------------------------------------
    fault_trial_id = f"trial-fault-{uuid4().hex[:8]}"
    fault_initial_fixture = fixture_manager.reset()

    # Verify equivalent logical starting state
    if fault_initial_fixture.record_count != clean_initial_fixture.record_count:
        fault_exec_status = ExecutionStatus.EXECUTION_ERROR
        fault_error_msg = (
            "Isolation breach: fault trial initial state does not match clean trial."
        )
        fault_evidence = TrialEvidence(
            trial_id=fault_trial_id,
            trial_role=TrialRole.FAULT,
            execution_status=fault_exec_status,
            clean_qualified=None,
            initial_fixture=fault_initial_fixture,
            final_fixture=fault_initial_fixture,
            intercepted_calls=[],
            total_calls_observed=0,
            duration_seconds=0.0,
            error_message=fault_error_msg,
        )
        exposure_status = ExposureStatus.EXPOSURE_UNKNOWN
    else:
        # Arm the one-shot BEFORE_EFFECT timeout episode
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
        fault_final_fixture = fixture_manager.observe()

        fault_evidence = TrialEvidence(
            trial_id=fault_trial_id,
            trial_role=TrialRole.FAULT,
            execution_status=fault_exec_status,
            clean_qualified=None,
            initial_fixture=fault_initial_fixture,
            final_fixture=fault_final_fixture,
            intercepted_calls=fault_interceptor.receipts,
            total_calls_observed=fault_interceptor.call_counter,
            duration_seconds=fault_duration,
            recovery_actor=RecoveryActor.AGENT
            if caller is not None
            else RecoveryActor.UNKNOWN,
            error_message=fault_error_msg,
        )

        # -------------------------------------------------------------------
        # 4. Exposure Classification
        # -------------------------------------------------------------------
        if not clean_qualified:
            # Failed clean control limits interpretation of fault trial
            exposure_status = ExposureStatus.EXPOSURE_UNKNOWN
        else:
            matching_receipt = next(
                (
                    r
                    for r in fault_interceptor.receipts
                    if r.tool_id == case.trigger.tool_id
                    and r.call_occurrence == case.trigger.call_occurrence
                ),
                None,
            )

            if matching_receipt is None:
                exposure_status = ExposureStatus.NOT_TRIGGERED
            else:
                if (
                    matching_receipt.reached_hook
                    and (not matching_receipt.forwarded_to_target)
                    and matching_receipt.fault_injected
                    and matching_receipt.caller_outcome == CallerOutcome.TIMEOUT
                ):
                    exposure_status = ExposureStatus.CONFIRMED
                else:
                    exposure_status = ExposureStatus.EXPOSURE_UNKNOWN

    # -----------------------------------------------------------------------
    # 5. Assemble Evidence Record
    # -----------------------------------------------------------------------
    matched_evidence = MatchedPairEvidence(
        schema_version="1.0.0",
        project_id=project_id,
        case_id=case_id,
        pair_id=pair_id,
        run_id=run_id,
        timestamp_utc=current_utc_iso(),
        case_snapshot=case_snapshot,
        recovery_contract_snapshot=recovery_contract_snapshot,
        adapter_version_snapshot=adapter_version_snapshot,
        environment_snapshot=environment_snapshot,
        clean_trial=clean_evidence,
        fault_trial=fault_evidence,
        exposure_status=exposure_status,
        recovery_verdict=None,  # Strictly null in Phase 2
        is_harness_demonstration=True,
        target_tool=adapter.tool_id,
        notes=[
            "Phase 2 demonstration: verified BEFORE_EFFECT timeout exposure.",
            "Clean and fault trials executed sequentially with isolated fixture reset.",
            "Recovery verdict is strictly null; final recovery scoring is deferred.",
        ],
    )

    if output_dir:
        save_evidence_artifact(matched_evidence, output_dir)

    return matched_evidence


def build_default_phase2_request() -> CaseValidationRequest:
    """Helper to build a valid Phase 2 candidate case request for the local runner."""
    from tests.test_c3_foundation import build_valid_test_request

    req = build_valid_test_request()
    # Update tool to NexaCart create_order tool
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
        description="Run C3 Phase 2 matched clean/fault trial pair demonstration."
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

    args = parser.parse_args()

    print("=== C3 Phase 2: Matched Clean/Fault Trial Runner ===")
    req = build_default_phase2_request()
    print(f"Target Tool: {req.case.tool_id}")
    print(f"Fault Family: {req.case.fault_family}")
    print(f"Effect Phase: {req.case.effect_phase}")
    print("Executing matched trials...")

    evidence = run_matched_pair(
        case=req.case,
        recovery_contract=req.recovery_contract,
        output_dir=args.output_dir,
        synthetic_timeout=args.synthetic,
        caller_timeout_seconds=args.caller_timeout,
    )

    print("\n=== Matched Pair Execution Complete ===")
    print(f"Pair ID:          {evidence.pair_id}")
    print(f"Clean Qualified:  {evidence.clean_trial.clean_qualified}")
    print(f"Exposure Status:  {evidence.exposure_status.value}")
    print(f"Recovery Verdict: {evidence.recovery_verdict} (Intentionally null)")
    print(f"Evidence Saved:   {args.output_dir}/matched_pair_{evidence.pair_id}.json")


if __name__ == "__main__":
    main()

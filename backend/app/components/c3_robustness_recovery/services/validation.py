"""
Deterministic static capability and case validator for Component 3 (C3):
Robustness and Failure Recovery Testing.

Pure deterministic logic:
- No database access or SQLAlchemy imports.
- No network access or external HTTP calls.
- No environment variable or .env inspection.
- No credential or raw input interpolation in messages.
"""

from app.components.c3_robustness_recovery.contracts.schemas import (
    APPLICATION_AWARE_HOOKS,
    CaseValidationRequest,
    CaseValidationResponse,
    EffectPhase,
    FaultCatalogResponse,
    FaultFamily,
    FaultFamilyDefinition,
    FaultParameterConstraints,
    MalformedMode,
    MalformedResponsePayload,
    RateLimit429Payload,
    ReleaseRuleMode,
    ServerError5xxPayload,
    TerminalOutcome,
    TimeoutMode,
    TimeoutPayload,
    ToolUnavailabilityPayload,
    UnavailabilityMode,
    ValidationReason,
    ValidationScope,
    ValidationStatus,
)

# Standard pending runtime checks required before any live experiment could be executed
PENDING_RUNTIME_CHECKS: list[str] = [
    "actual_fixture_reset",
    "trigger_reachability",
    "observation_access",
    "injection_effect_phase_fidelity_verification",
]


def get_operational_fault_catalog() -> FaultCatalogResponse:
    """
    Returns the five operational fault families, parameter constraints,
    and explicit indication that injection is not implemented in Phase 1.
    """
    return FaultCatalogResponse(
        catalog_version="1.0.0",
        phase="Phase 1 - Static Foundation",
        injection_implemented=False,
        disclaimer=(
            "Fault injection is NOT implemented in Phase 1. Catalogue entries define supported operational "
            "fault families and parameter constraints for static capability and case validation. Catalogue "
            "availability does not imply adapter support or runtime exposure."
        ),
        families=[
            FaultFamilyDefinition(
                family=FaultFamily.TIMEOUT_OR_DISCONNECTION,
                display_name="Timeout or Disconnection",
                description=(
                    "Simulates transport-level disconnection, socket drop, or delayed response "
                    "exceeding client timeout boundaries."
                ),
                parameter_constraints=FaultParameterConstraints(
                    allowed_modes=[mode.value for mode in TimeoutMode],
                    timing_bounds={"min_delay_ms": 1, "max_delay_ms": 300000},
                    release_rule_modes=[
                        ReleaseRuleMode.SINGLE_CALL,
                        ReleaseRuleMode.COUNT_BASED,
                        ReleaseRuleMode.TIME_BASED,
                    ],
                ),
                supported_effect_phases=[
                    EffectPhase.BEFORE_EFFECT,
                    EffectPhase.AFTER_COMMIT,
                    EffectPhase.NOT_APPLICABLE,
                ],
                requires_application_aware_hook_for_commit=True,
                injection_status="NOT_IMPLEMENTED",
            ),
            FaultFamilyDefinition(
                family=FaultFamily.TRANSIENT_5XX_SERVER_ERROR,
                display_name="Transient 5xx Server Response",
                description=(
                    "Simulates upstream server failures returning HTTP status 500-599. "
                    "Note: Not all 5xx errors are safe to retry; duplicate side effects must be avoided."
                ),
                parameter_constraints=FaultParameterConstraints(
                    allowed_modes=[
                        "INTERNAL_SERVER_ERROR_500",
                        "BAD_GATEWAY_502",
                        "SERVICE_UNAVAILABLE_503",
                        "GATEWAY_TIMEOUT_504",
                    ],
                    status_code_bounds={"min_status_code": 500, "max_status_code": 599},
                    release_rule_modes=[
                        ReleaseRuleMode.SINGLE_CALL,
                        ReleaseRuleMode.COUNT_BASED,
                    ],
                ),
                supported_effect_phases=[
                    EffectPhase.BEFORE_EFFECT,
                    EffectPhase.AFTER_COMMIT,
                    EffectPhase.NOT_APPLICABLE,
                ],
                requires_application_aware_hook_for_commit=True,
                injection_status="NOT_IMPLEMENTED",
            ),
            FaultFamilyDefinition(
                family=FaultFamily.HTTP_429_RATE_LIMITING,
                display_name="HTTP 429 Rate Limiting",
                description=(
                    "Simulates rate limit throttling with HTTP status 429 and optional non-negative "
                    "Retry-After backoff duration."
                ),
                parameter_constraints=FaultParameterConstraints(
                    allowed_modes=["TOO_MANY_REQUESTS_429"],
                    status_code_bounds={"status_code": 429},
                    retry_after_bounds={
                        "min_retry_after_seconds": 0,
                        "max_retry_after_seconds": 86400,
                    },
                    release_rule_modes=[
                        ReleaseRuleMode.SINGLE_CALL,
                        ReleaseRuleMode.COUNT_BASED,
                        ReleaseRuleMode.TIME_BASED,
                    ],
                ),
                supported_effect_phases=[
                    EffectPhase.BEFORE_EFFECT,
                    EffectPhase.NOT_APPLICABLE,
                ],
                requires_application_aware_hook_for_commit=False,
                injection_status="NOT_IMPLEMENTED",
            ),
            FaultFamilyDefinition(
                family=FaultFamily.TOOL_UNAVAILABILITY,
                display_name="Tool Unavailability",
                description=(
                    "Simulates declared tool outages, circuit breaker trips, or scheduled maintenance "
                    "with bounded release duration."
                ),
                parameter_constraints=FaultParameterConstraints(
                    allowed_modes=[mode.value for mode in UnavailabilityMode],
                    timing_bounds={"max_downtime_seconds": 3600},
                    release_rule_modes=[
                        ReleaseRuleMode.SINGLE_CALL,
                        ReleaseRuleMode.COUNT_BASED,
                        ReleaseRuleMode.TIME_BASED,
                    ],
                ),
                supported_effect_phases=[
                    EffectPhase.BEFORE_EFFECT,
                    EffectPhase.NOT_APPLICABLE,
                ],
                requires_application_aware_hook_for_commit=False,
                injection_status="NOT_IMPLEMENTED",
            ),
            FaultFamilyDefinition(
                family=FaultFamily.MALFORMED_OR_TRUNCATED_RESPONSE,
                display_name="Malformed or Truncated Tool Response",
                description=(
                    "Simulates corrupted payloads, syntactically malformed JSON, or schema-violating tool replies."
                ),
                parameter_constraints=FaultParameterConstraints(
                    allowed_modes=[mode.value for mode in MalformedMode],
                    release_rule_modes=[
                        ReleaseRuleMode.SINGLE_CALL,
                        ReleaseRuleMode.COUNT_BASED,
                    ],
                ),
                supported_effect_phases=[
                    EffectPhase.BEFORE_EFFECT,
                    EffectPhase.AFTER_COMMIT,
                    EffectPhase.NOT_APPLICABLE,
                ],
                requires_application_aware_hook_for_commit=True,
                injection_status="NOT_IMPLEMENTED",
            ),
        ],
    )


def validate_candidate_case(request: CaseValidationRequest) -> CaseValidationResponse:
    """
    Pure deterministic validation of declared metadata, capability alignments,
    and contract consistency.

    Returns HTTP 200 equivalent CaseValidationResponse with STATIC_VALID or TEST_NOT_READY.
    """
    reasons: list[ValidationReason] = []
    case = request.case
    adapter = request.adapter_manifest
    contract = request.recovery_contract
    env = request.environment_metadata

    # 1. Reference & Version consistency checks
    if case.adapter_id != adapter.adapter_id:
        reasons.append(
            ValidationReason(
                code="ADAPTER_REFERENCE_MISMATCH",
                message="Case adapter_id does not match adapter manifest identifier.",
                field_path="case.adapter_id",
            )
        )

    if case.adapter_version != adapter.adapter_version:
        reasons.append(
            ValidationReason(
                code="ADAPTER_VERSION_MISMATCH",
                message="Case adapter_version does not match adapter manifest version.",
                field_path="case.adapter_version",
            )
        )

    if case.recovery_contract_id != contract.contract_id:
        reasons.append(
            ValidationReason(
                code="RECOVERY_CONTRACT_REFERENCE_MISMATCH",
                message="Case recovery_contract_id does not match recovery contract identifier.",
                field_path="case.recovery_contract_id",
            )
        )

    if case.recovery_contract_version != contract.version:
        reasons.append(
            ValidationReason(
                code="RECOVERY_CONTRACT_VERSION_MISMATCH",
                message="Case recovery_contract_version does not match recovery contract version.",
                field_path="case.recovery_contract_version",
            )
        )

    if case.task_id != env.task.task_id:
        reasons.append(
            ValidationReason(
                code="TASK_REFERENCE_MISMATCH",
                message="Case task_id does not match environment task identifier.",
                field_path="case.task_id",
            )
        )

    if case.task_version != env.task.task_version:
        reasons.append(
            ValidationReason(
                code="TASK_VERSION_MISMATCH",
                message="Case task_version does not match environment task version.",
                field_path="case.task_version",
            )
        )

    if case.fixture_id != env.fixture.fixture_id:
        reasons.append(
            ValidationReason(
                code="FIXTURE_REFERENCE_MISMATCH",
                message="Case fixture_id does not match environment fixture identifier.",
                field_path="case.fixture_id",
            )
        )

    if case.fixture_version != env.fixture.fixture_version:
        reasons.append(
            ValidationReason(
                code="FIXTURE_VERSION_MISMATCH",
                message="Case fixture_version does not match environment fixture version.",
                field_path="case.fixture_version",
            )
        )

    # 2. Selected tool checks in adapter manifest
    tool_match = next((t for t in adapter.tools if t.tool_id == case.tool_id), None)
    if tool_match is None:
        reasons.append(
            ValidationReason(
                code="TOOL_NOT_IN_MANIFEST",
                message="Target tool is not declared in adapter capability manifest.",
                field_path="case.tool_id",
            )
        )
    else:
        if tool_match.tool_version != case.tool_version:
            reasons.append(
                ValidationReason(
                    code="TOOL_VERSION_MISMATCH",
                    message="Case tool_version does not match tool declaration version in adapter manifest.",
                    field_path="case.tool_version",
                )
            )

        # Mutability vs effect phase rules
        if not tool_match.is_side_effecting:
            if case.effect_phase in (
                EffectPhase.AFTER_COMMIT,
                EffectPhase.PARTIAL_EFFECT,
            ):
                reasons.append(
                    ValidationReason(
                        code="READ_ONLY_TOOL_EFFECT_PHASE_INCOMPATIBLE",
                        message="Read-only tools cannot declare AFTER_COMMIT or PARTIAL_EFFECT phases.",
                        field_path="case.effect_phase",
                    )
                )
        else:
            if case.effect_phase == EffectPhase.NOT_APPLICABLE:
                reasons.append(
                    ValidationReason(
                        code="SIDE_EFFECTING_TOOL_PHASE_INVALID",
                        message="Side-effecting tools cannot declare NOT_APPLICABLE effect phase.",
                        field_path="case.effect_phase",
                    )
                )

    # 3. Specific rules for PARTIAL_EFFECT and AFTER_COMMIT
    if case.effect_phase == EffectPhase.PARTIAL_EFFECT:
        if case.trigger.hook not in APPLICATION_AWARE_HOOKS:
            reasons.append(
                ValidationReason(
                    code="PARTIAL_EFFECT_REQUIRES_APPLICATION_AWARE_HOOK",
                    message="PARTIAL_EFFECT requires an application-aware hook, not a generic transport/network hook.",
                    field_path="case.trigger.hook",
                )
            )
        if not env.fixture.has_partial_effect_observation:
            reasons.append(
                ValidationReason(
                    code="PARTIAL_EFFECT_MISSING_OBSERVATION",
                    message="PARTIAL_EFFECT requires fixture metadata declaring observable partial effects.",
                    field_path="environment_metadata.fixture.has_partial_effect_observation",
                )
            )

    if case.effect_phase == EffectPhase.AFTER_COMMIT:
        # AFTER_COMMIT requires an application-aware hook
        if case.trigger.hook not in APPLICATION_AWARE_HOOKS:
            reasons.append(
                ValidationReason(
                    code="AFTER_COMMIT_REQUIRES_APPLICATION_AWARE_HOOK",
                    message="AFTER_COMMIT effect phase requires an application-aware hook, not a generic transport/network hook.",
                    field_path="case.trigger.hook",
                )
            )

        # AFTER_COMMIT requires independent commit observation capability in fixture metadata
        if not env.fixture.has_commit_observation:
            reasons.append(
                ValidationReason(
                    code="AFTER_COMMIT_MISSING_COMMIT_OBSERVATION",
                    message="AFTER_COMMIT effect phase requires fixture metadata declaring independent commit observation capability.",
                    field_path="environment_metadata.fixture.has_commit_observation",
                )
            )

    # 4. Explicit capability combination check (must NOT infer from cross-product)
    matched_cap = next(
        (
            c
            for c in adapter.capabilities
            if c.fault_family == case.fault_family
            and c.effect_phase == case.effect_phase
            and c.hook == case.trigger.hook
            and case.release_rule.mode in c.supported_release_modes
            and (c.tool_id is None or c.tool_id == case.tool_id)
            and (
                c.max_call_occurrence is None
                or case.trigger.call_occurrence <= c.max_call_occurrence
            )
        ),
        None,
    )

    if matched_cap is None:
        reasons.append(
            ValidationReason(
                code="CAPABILITY_COMBINATION_NOT_DECLARED",
                message="The exact combination of fault family, effect phase, hook, and release rule is not declared in the adapter capability manifest.",
                field_path="adapter_manifest.capabilities",
            )
        )
    else:
        # Check application awareness alignment
        if (
            case.effect_phase == EffectPhase.AFTER_COMMIT
            and not matched_cap.is_application_aware
        ):
            reasons.append(
                ValidationReason(
                    code="CAPABILITY_NOT_APPLICATION_AWARE",
                    message="Matched adapter capability is not declared as application-aware for AFTER_COMMIT delivery.",
                    field_path="adapter_manifest.capabilities",
                )
            )

        # Check payload constraints against declared capability boundaries
        if isinstance(case.payload, TimeoutPayload):
            if (
                matched_cap.allowed_modes
                and case.payload.mode.value not in matched_cap.allowed_modes
            ):
                reasons.append(
                    ValidationReason(
                        code="PAYLOAD_MODE_NOT_SUPPORTED",
                        message="Timeout mode is not supported by the declared capability.",
                        field_path="case.payload.mode",
                    )
                )
            if (
                matched_cap.min_delay_ms is not None
                and case.payload.delay_ms < matched_cap.min_delay_ms
            ):
                reasons.append(
                    ValidationReason(
                        code="PAYLOAD_DELAY_BELOW_MINIMUM",
                        message="Payload timeout delay is below capability declared minimum delay.",
                        field_path="case.payload.delay_ms",
                    )
                )
            if (
                matched_cap.max_delay_ms is not None
                and case.payload.delay_ms > matched_cap.max_delay_ms
            ):
                reasons.append(
                    ValidationReason(
                        code="PAYLOAD_DELAY_EXCEEDS_MAXIMUM",
                        message="Payload timeout delay exceeds capability declared maximum delay.",
                        field_path="case.payload.delay_ms",
                    )
                )
        elif isinstance(case.payload, ServerError5xxPayload):
            if (
                matched_cap.allowed_status_codes
                and case.payload.status_code not in matched_cap.allowed_status_codes
            ):
                reasons.append(
                    ValidationReason(
                        code="STATUS_CODE_NOT_SUPPORTED",
                        message="Server error status code is not supported by the declared capability.",
                        field_path="case.payload.status_code",
                    )
                )
        elif isinstance(case.payload, RateLimit429Payload):
            if (
                case.payload.retry_after_seconds is not None
                and matched_cap.max_retry_after_seconds is not None
                and case.payload.retry_after_seconds
                > matched_cap.max_retry_after_seconds
            ):
                reasons.append(
                    ValidationReason(
                        code="RETRY_AFTER_EXCEEDS_MAXIMUM",
                        message="Rate limit retry_after_seconds exceeds capability declared maximum.",
                        field_path="case.payload.retry_after_seconds",
                    )
                )
        elif isinstance(case.payload, ToolUnavailabilityPayload):
            if (
                matched_cap.allowed_modes
                and case.payload.mode.value not in matched_cap.allowed_modes
            ):
                reasons.append(
                    ValidationReason(
                        code="UNAVAILABILITY_MODE_NOT_SUPPORTED",
                        message="Tool unavailability mode is not supported by the declared capability.",
                        field_path="case.payload.mode",
                    )
                )
        elif isinstance(case.payload, MalformedResponsePayload):
            if (
                matched_cap.allowed_modes
                and case.payload.mode.value not in matched_cap.allowed_modes
            ):
                reasons.append(
                    ValidationReason(
                        code="MALFORMED_MODE_NOT_SUPPORTED",
                        message="Malformed response mode is not supported by the declared capability.",
                        field_path="case.payload.mode",
                    )
                )

        # Observation method declared by capability must exist in environment metadata
        obs_method_ids = {om.method_id for om in env.observation_methods}
        if matched_cap.observation_method not in obs_method_ids:
            reasons.append(
                ValidationReason(
                    code="OBSERVATION_METHOD_NOT_FOUND",
                    message="Capability observation method is not declared in environment observation metadata.",
                    field_path="adapter_manifest.capabilities.observation_method",
                )
            )

    # 5. Assertion reference checks
    available_assertion_ids = {a.assertion_id for a in env.available_assertions}
    missing_case_assertions = [
        aid for aid in case.required_assertion_ids if aid not in available_assertion_ids
    ]
    if missing_case_assertions:
        reasons.append(
            ValidationReason(
                code="CASE_ASSERTION_NOT_FOUND",
                message="One or more case required assertions are not declared in environment assertion metadata.",
                field_path="case.required_assertion_ids",
            )
        )

    missing_contract_assertions = [
        aid
        for aid in contract.required_assertion_ids
        if aid not in available_assertion_ids
    ]
    if missing_contract_assertions:
        reasons.append(
            ValidationReason(
                code="RECOVERY_ASSERTION_NOT_FOUND",
                message="One or more recovery contract required assertions are not declared in environment assertion metadata.",
                field_path="recovery_contract.required_assertion_ids",
            )
        )

    # 6. Fixture reset and observation support checks
    if not env.fixture.supports_reset:
        reasons.append(
            ValidationReason(
                code="FIXTURE_RESET_NOT_SUPPORTED",
                message="Fixture metadata does not declare required state reset support.",
                field_path="environment_metadata.fixture.supports_reset",
            )
        )

    if not env.fixture.supports_observation:
        reasons.append(
            ValidationReason(
                code="FIXTURE_OBSERVATION_NOT_SUPPORTED",
                message="Fixture metadata does not declare required state observation support.",
                field_path="environment_metadata.fixture.supports_observation",
            )
        )

    # 7. Recovery contract budget & outcome consistency
    if contract.max_total_attempts < 1:
        reasons.append(
            ValidationReason(
                code="INVALID_ATTEMPT_BUDGET",
                message="max_total_attempts must be at least 1.",
                field_path="recovery_contract.max_total_attempts",
            )
        )

    if contract.max_retries < 0:
        reasons.append(
            ValidationReason(
                code="INVALID_RETRY_BUDGET",
                message="max_retries must be non-negative.",
                field_path="recovery_contract.max_retries",
            )
        )

    if contract.max_retries >= contract.max_total_attempts:
        reasons.append(
            ValidationReason(
                code="CONTRADICTORY_ATTEMPT_BUDGET",
                message="max_retries must be strictly less than max_total_attempts as attempt 1 represents the initial call.",
                field_path="recovery_contract.max_retries",
            )
        )

    if contract.timeout_budget_seconds <= 0.0:
        reasons.append(
            ValidationReason(
                code="INVALID_TIMEOUT_BUDGET",
                message="timeout_budget_seconds must be positive.",
                field_path="recovery_contract.timeout_budget_seconds",
            )
        )

    if isinstance(case.payload, TimeoutPayload):
        delay_sec = case.payload.delay_ms / 1000.0
        if case.caller_timeout_seconds is not None:
            if case.caller_timeout_seconds >= contract.timeout_budget_seconds:
                reasons.append(
                    ValidationReason(
                        code="CALLER_TIMEOUT_EXCEEDS_BUDGET",
                        message="Caller timeout boundary is greater than or equal to recovery timeout budget.",
                        field_path="case.caller_timeout_seconds",
                    )
                )
        else:
            if delay_sec >= contract.timeout_budget_seconds:
                reasons.append(
                    ValidationReason(
                        code="FAULT_DELAY_EXCEEDS_TIMEOUT_BUDGET",
                        message="Fault injection delay is greater than or equal to recovery timeout budget.",
                        field_path="case.payload.delay_ms",
                    )
                )

    if (
        case.release_rule.mode == ReleaseRuleMode.TIME_BASED
        and case.release_rule.duration_seconds is not None
    ):
        if case.release_rule.duration_seconds > contract.timeout_budget_seconds:
            reasons.append(
                ValidationReason(
                    code="RELEASE_RULE_EXCEEDS_TIMEOUT_BUDGET",
                    message="Fault release rule duration exceeds recovery timeout budget.",
                    field_path="case.release_rule.duration_seconds",
                )
            )

    non_fail_outcomes = [
        o for o in contract.permitted_terminal_outcomes if o != TerminalOutcome.FAIL
    ]
    if not non_fail_outcomes:
        reasons.append(
            ValidationReason(
                code="NO_PERMITTED_NON_FAILURE_OUTCOME",
                message="Recovery contract must specify at least one permitted non-failure terminal outcome.",
                field_path="recovery_contract.permitted_terminal_outcomes",
            )
        )

    if (
        case.release_rule.mode == ReleaseRuleMode.COUNT_BASED
        and case.release_rule.max_fault_occurrences is not None
    ):
        if case.release_rule.max_fault_occurrences > contract.max_total_attempts:
            reasons.append(
                ValidationReason(
                    code="RELEASE_RULE_EXCEEDS_ATTEMPT_BUDGET",
                    message="Fault release rule requires more fault occurrences than total attempt budget allows.",
                    field_path="case.release_rule.max_fault_occurrences",
                )
            )

    # 8. Final verdict assembly
    if reasons:
        return CaseValidationResponse(
            validation_scope=ValidationScope.STATIC_ONLY,
            validation_status=ValidationStatus.TEST_NOT_READY,
            execution_ready=False,
            pending_checks=[],
            reasons=reasons,
            recovery_verdict=None,
        )

    return CaseValidationResponse(
        validation_scope=ValidationScope.STATIC_ONLY,
        validation_status=ValidationStatus.STATIC_VALID,
        execution_ready=False,
        pending_checks=PENDING_RUNTIME_CHECKS,
        reasons=[],
        recovery_verdict=None,
    )

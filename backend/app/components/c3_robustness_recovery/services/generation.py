"""
Candidate fault case generation and bounded suite selection service for Component 3 (C3) Phase 4.

Features:
- Pure deterministic generation without database, network, LLM, or runner side effects.
- Direct derivation from explicit adapter capability combination records (no blind cross-products).
- Automatic resolution of compatible task, tool, fixture, and recovery references.
- Bounded sampling across 5 operational catalogue fault families.
- Examination budget stopping and explicit truncation reporting.
- Strict static validation of every generated candidate via services/validation.py.
- Semantic fingerprinting and deduplication (excluding generated IDs and timestamps).
- Deterministic seeded round-robin selection across (tool, fault_family) groups.
- Frozen suite assembly with content-addressed SHA-256 digest.
"""

from collections import defaultdict
from datetime import datetime, timezone
import random
from typing import Any

from app.components.c3_robustness_recovery.contracts.generation import (
    CaseGenerationRequest,
    CaseGenerationResponse,
    CoverageSummary,
    FrozenSuite,
    GenerationCounters,
    GenerationStatus,
)
from app.components.c3_robustness_recovery.contracts.schemas import (
    AdapterCapability,
    CandidateFaultCase,
    CaseValidationRequest,
    EffectPhase,
    EnvironmentMetadata,
    FaultFamily,
    FixtureMetadata,
    MalformedMode,
    MalformedResponsePayload,
    RateLimit429Payload,
    RecoveryContract,
    ReleaseRule,
    ReleaseRuleMode,
    ServerError5xxPayload,
    TaskMetadata,
    TimeoutMode,
    TimeoutPayload,
    ToolUnavailabilityPayload,
    TriggerDefinition,
    UnavailabilityMode,
    ValidationReason,
    ValidationScope,
    ValidationStatus,
)
from app.components.c3_robustness_recovery.services.suites import (
    compute_case_semantic_fingerprint,
    compute_suite_content_digest,
)
from app.components.c3_robustness_recovery.services.validation import (
    validate_candidate_case,
)


def _canonical_sort_key(item: Any) -> str:
    """Extract a stable string sort key from metadata models."""
    if hasattr(item, "tool_id"):
        return str(getattr(item, "tool_id"))
    if hasattr(item, "task_id"):
        return str(getattr(item, "task_id"))
    if hasattr(item, "fixture_id"):
        return str(getattr(item, "fixture_id"))
    if hasattr(item, "adapter_id"):
        return str(getattr(item, "adapter_id"))
    if hasattr(item, "contract_id"):
        return str(getattr(item, "contract_id"))
    if hasattr(item, "assertion_id"):
        return str(getattr(item, "assertion_id"))
    if hasattr(item, "method_id"):
        return str(getattr(item, "method_id"))
    return str(item)


def _derive_payload_variants(
    capability: AdapterCapability,
) -> list[
    TimeoutPayload
    | ServerError5xxPayload
    | RateLimit429Payload
    | ToolUnavailabilityPayload
    | MalformedResponsePayload
]:
    """Derive representative and boundary payload variants within declared capability constraints."""
    variants = []
    family = capability.fault_family

    if family == FaultFamily.TIMEOUT_OR_DISCONNECTION:
        modes = capability.allowed_modes or [
            TimeoutMode.CONNECTION_TIMEOUT.value,
            TimeoutMode.READ_TIMEOUT.value,
        ]
        min_d = capability.min_delay_ms or 100
        max_d = capability.max_delay_ms or 5000
        delays = [min_d] if min_d == max_d else [min_d, max_d]
        for m_str in modes:
            try:
                m = TimeoutMode(m_str)
                for d in delays:
                    variants.append(
                        TimeoutPayload(
                            family=FaultFamily.TIMEOUT_OR_DISCONNECTION,
                            mode=m,
                            delay_ms=d,
                        )
                    )
            except ValueError:
                continue

    elif family == FaultFamily.TRANSIENT_5XX_SERVER_ERROR:
        status_codes = capability.allowed_status_codes or [500, 503]
        for sc in status_codes:
            variants.append(
                ServerError5xxPayload(
                    family=FaultFamily.TRANSIENT_5XX_SERVER_ERROR,
                    status_code=sc,
                    error_message=(
                        "Service Unavailable" if sc == 503 else "Internal Server Error"
                    ),
                )
            )

    elif family == FaultFamily.HTTP_429_RATE_LIMITING:
        max_ra = (
            capability.max_retry_after_seconds
            if capability.max_retry_after_seconds is not None
            else 60
        )
        ra_samples = [0, min(5, max_ra)] if max_ra > 0 else [0]
        for ra in set(ra_samples):
            variants.append(
                RateLimit429Payload(
                    family=FaultFamily.HTTP_429_RATE_LIMITING,
                    status_code=429,
                    retry_after_seconds=ra,
                    error_message="Too Many Requests",
                )
            )

    elif family == FaultFamily.TOOL_UNAVAILABILITY:
        modes = capability.allowed_modes or [
            UnavailabilityMode.CIRCUIT_BREAKER_OPEN.value,
            UnavailabilityMode.MAINTENANCE_MODE.value,
        ]
        for m_str in modes:
            try:
                m = UnavailabilityMode(m_str)
                variants.append(
                    ToolUnavailabilityPayload(
                        family=FaultFamily.TOOL_UNAVAILABILITY,
                        mode=m,
                        error_message=f"Tool unavailable: {m.value}",
                        expected_downtime_seconds=60.0,
                    )
                )
            except ValueError:
                continue

    elif family == FaultFamily.MALFORMED_OR_TRUNCATED_RESPONSE:
        modes = capability.allowed_modes or [
            MalformedMode.INVALID_JSON.value,
            MalformedMode.TRUNCATED_JSON.value,
        ]
        for m_str in modes:
            try:
                m = MalformedMode(m_str)
                frag = (
                    "{" if m == MalformedMode.TRUNCATED_JSON else "<html>Error</html>"
                )
                variants.append(
                    MalformedResponsePayload(
                        family=FaultFamily.MALFORMED_OR_TRUNCATED_RESPONSE,
                        mode=m,
                        raw_fragment=frag,
                    )
                )
            except ValueError:
                continue

    return variants


def _derive_release_rule(capability: AdapterCapability) -> ReleaseRule:
    """Select the primary supported release rule mode declared by the capability."""
    modes = capability.supported_release_modes
    if ReleaseRuleMode.SINGLE_CALL in modes:
        return ReleaseRule(mode=ReleaseRuleMode.SINGLE_CALL, max_fault_occurrences=1)
    if ReleaseRuleMode.COUNT_BASED in modes:
        return ReleaseRule(mode=ReleaseRuleMode.COUNT_BASED, max_fault_occurrences=1)
    if ReleaseRuleMode.TIME_BASED in modes:
        return ReleaseRule(mode=ReleaseRuleMode.TIME_BASED, duration_seconds=5.0)
    return ReleaseRule(mode=ReleaseRuleMode.SINGLE_CALL, max_fault_occurrences=1)


def generate_fault_suite(request: CaseGenerationRequest) -> CaseGenerationResponse:
    """
    Pure candidate generation and frozen suite selection algorithm.
    Guarantees:
    - Same canonical inputs, generator version, policy, and seed produce identical selected cases and digest.
    - Completely ignores irrelevant input array ordering.
    - Statically validates every candidate against existing C3 validation rules.
    - Strictly obeys max_candidates_examined and max_cases budgets.
    """
    # 1. Canonicalize input collections to ensure input ordering independence
    sorted_tasks = sorted(request.tasks, key=_canonical_sort_key)
    sorted_manifests = sorted(request.adapter_manifests, key=_canonical_sort_key)
    sorted_fixtures = sorted(request.fixtures, key=_canonical_sort_key)
    sorted_contracts = sorted(request.recovery_contracts, key=_canonical_sort_key)
    sorted_assertions = sorted(request.available_assertions, key=_canonical_sort_key)
    sorted_obs_methods = sorted(request.observation_methods, key=_canonical_sort_key)

    filter_tools = (
        set(request.filters.tool_ids)
        if request.filters and request.filters.tool_ids
        else None
    )
    filter_families = (
        set(request.filters.fault_families)
        if request.filters and request.filters.fault_families
        else None
    )
    filter_phases = (
        set(request.filters.effect_phases)
        if request.filters and request.filters.effect_phases
        else None
    )

    # Trackers and counters
    examined_count = 0
    valid_count = 0
    rejected_count = 0
    duplicate_count = 0
    is_truncated = False
    max_budget = request.policy.max_candidates_examined

    unique_candidates: dict[str, CandidateFaultCase] = {}
    candidate_case_families: dict[str, str] = {}
    candidate_recovery_contracts: dict[str, RecoveryContract] = {}
    rejected_summaries: list[ValidationReason] = []
    skipped_summaries: list[dict[str, Any]] = []

    eligible_tools: set[str] = set()
    eligible_families: set[FaultFamily] = set()

    # 2. Derive candidates from explicit capability combinations
    for manifest in sorted_manifests:
        # Sort tools and capabilities within manifest
        manifest_tools = sorted(manifest.tools, key=lambda t: t.tool_id)
        manifest_caps = sorted(
            manifest.capabilities,
            key=lambda c: (
                c.fault_family.value,
                c.effect_phase.value,
                c.hook.value,
                c.tool_id or "",
            ),
        )

        for cap in manifest_caps:
            # Find matching declared tools for this capability
            if cap.tool_id:
                matching_tools = [t for t in manifest_tools if t.tool_id == cap.tool_id]
            else:
                matching_tools = manifest_tools

            for tool in matching_tools:
                eligible_tools.add(tool.tool_id)
                eligible_families.add(cap.fault_family)

                # Check filters early
                if filter_tools and tool.tool_id not in filter_tools:
                    skipped_summaries.append(
                        {
                            "tool_id": tool.tool_id,
                            "family": cap.fault_family.value,
                            "phase": cap.effect_phase.value,
                            "reason": "Filtered out by tool_ids filter.",
                        }
                    )
                    continue
                if filter_families and cap.fault_family not in filter_families:
                    skipped_summaries.append(
                        {
                            "tool_id": tool.tool_id,
                            "family": cap.fault_family.value,
                            "phase": cap.effect_phase.value,
                            "reason": "Filtered out by fault_families filter.",
                        }
                    )
                    continue
                if filter_phases and cap.effect_phase not in filter_phases:
                    skipped_summaries.append(
                        {
                            "tool_id": tool.tool_id,
                            "family": cap.fault_family.value,
                            "phase": cap.effect_phase.value,
                            "reason": "Filtered out by effect_phases filter.",
                        }
                    )
                    continue

                # Find compatible fixture
                compatible_fixture: FixtureMetadata | None = None
                for fix in sorted_fixtures:
                    if not (fix.supports_reset and fix.supports_observation):
                        continue
                    if (
                        cap.effect_phase == EffectPhase.AFTER_COMMIT
                        and not fix.has_commit_observation
                    ):
                        continue
                    if (
                        cap.effect_phase == EffectPhase.PARTIAL_EFFECT
                        and not fix.has_partial_effect_observation
                    ):
                        continue
                    compatible_fixture = fix
                    break

                if not compatible_fixture:
                    rejected_summaries.append(
                        ValidationReason(
                            code="NO_COMPATIBLE_FIXTURE",
                            message=f"No fixture found satisfying observation and reset requirements for {cap.effect_phase.value}.",
                            field_path="fixtures",
                        )
                    )
                    continue

                # Find compatible task
                compatible_task: TaskMetadata | None = (
                    sorted_tasks[0] if sorted_tasks else None
                )
                if not compatible_task:
                    rejected_summaries.append(
                        ValidationReason(
                            code="NO_COMPATIBLE_TASK",
                            message="No task definitions available to associate with candidate case.",
                            field_path="tasks",
                        )
                    )
                    continue

                # Find compatible recovery contract
                available_assertion_ids = {a.assertion_id for a in sorted_assertions}
                compatible_contract: RecoveryContract | None = None
                for rc in sorted_contracts:
                    if all(
                        aid in available_assertion_ids
                        for aid in rc.required_assertion_ids
                    ):
                        compatible_contract = rc
                        break

                if not compatible_contract:
                    rejected_summaries.append(
                        ValidationReason(
                            code="NO_COMPATIBLE_RECOVERY_CONTRACT",
                            message="No recovery contract found with all required assertions satisfied by available assertions.",
                            field_path="recovery_contracts",
                        )
                    )
                    continue

                # Determine trigger occurrences to sample
                max_occ = cap.max_call_occurrence or 1
                occurrences = [1] if max_occ == 1 else [1, min(2, max_occ)]

                # Derive release rule and payload variants
                release_rule = _derive_release_rule(cap)
                payload_variants = _derive_payload_variants(cap)

                # Assemble candidates
                for occ in occurrences:
                    for payload in payload_variants:
                        if examined_count >= max_budget:
                            is_truncated = True
                            break

                        examined_count += 1

                        caller_timeout = (
                            2.0
                            if cap.fault_family == FaultFamily.TIMEOUT_OR_DISCONNECTION
                            else None
                        )

                        # Temporary placeholder case for fingerprint derivation
                        temp_case = CandidateFaultCase(
                            schema_version="1.0.0",
                            project_id=request.project_id,
                            case_id="case-placeholder",
                            case_family=f"fam-{tool.tool_id}-{cap.fault_family.value.lower()}-{cap.effect_phase.value.lower()}",
                            domain=compatible_task.domain,
                            task_id=compatible_task.task_id,
                            task_version=compatible_task.task_version,
                            tool_id=tool.tool_id,
                            tool_version=tool.tool_version,
                            fixture_id=compatible_fixture.fixture_id,
                            fixture_version=compatible_fixture.fixture_version,
                            adapter_id=manifest.adapter_id,
                            adapter_version=manifest.adapter_version,
                            recovery_contract_id=compatible_contract.contract_id,
                            recovery_contract_version=compatible_contract.version,
                            trigger=TriggerDefinition(
                                tool_id=tool.tool_id,
                                call_occurrence=occ,
                                hook=cap.hook,
                            ),
                            fault_family=cap.fault_family,
                            effect_phase=cap.effect_phase,
                            payload=payload,
                            release_rule=release_rule,
                            required_assertion_ids=compatible_contract.required_assertion_ids,
                            seed=request.seed,
                            caller_timeout_seconds=caller_timeout,
                        )

                        # Compute semantic fingerprint (excludes case_id, seed, display)
                        fp = compute_case_semantic_fingerprint(temp_case)
                        case_id = f"case-{fp[:8]}"
                        case_family = temp_case.case_family

                        # Create candidate with stable deterministic identity
                        candidate = temp_case.model_copy(update={"case_id": case_id})

                        # 3. Static validation pass through existing validator
                        env_meta = EnvironmentMetadata(
                            task=compatible_task,
                            fixture=compatible_fixture,
                            available_assertions=sorted_assertions,
                            observation_methods=sorted_obs_methods,
                        )
                        val_req = CaseValidationRequest(
                            case=candidate,
                            adapter_manifest=manifest,
                            recovery_contract=compatible_contract,
                            environment_metadata=env_meta,
                        )
                        val_res = validate_candidate_case(val_req)

                        if val_res.validation_status != ValidationStatus.STATIC_VALID:
                            rejected_count += 1
                            rejected_summaries.extend(val_res.reasons)
                            continue

                        valid_count += 1

                        # 4. Semantic deduplication
                        if fp in unique_candidates:
                            duplicate_count += 1
                        else:
                            unique_candidates[fp] = candidate
                            candidate_case_families[case_id] = case_family
                            candidate_recovery_contracts[
                                compatible_contract.contract_id
                            ] = compatible_contract

                    if is_truncated:
                        break
                if is_truncated:
                    break
            if is_truncated:
                break
        if is_truncated:
            break

    # 5. Deterministic Bounded Selection (Round-Robin across (tool_id, fault_family) groups)
    groups: dict[tuple[str, FaultFamily], list[CandidateFaultCase]] = defaultdict(list)
    for fp, c in unique_candidates.items():
        groups[(c.tool_id, c.fault_family)].append(c)

    sorted_group_keys = sorted(groups.keys(), key=lambda k: (k[0], k[1].value))

    # Sort items within each group by case_id for baseline determinism
    for k in sorted_group_keys:
        groups[k].sort(key=lambda c: c.case_id)
        if request.seed is not None:
            # Deterministic seeded shuffle
            rng = random.Random(request.seed + hash(k) % 10000)
            rng.shuffle(groups[k])

    selected_cases: list[CandidateFaultCase] = []
    max_cases = request.policy.max_cases
    active_keys = [k for k in sorted_group_keys if groups[k]]

    while len(selected_cases) < max_cases and active_keys:
        next_active_keys = []
        for k in active_keys:
            if groups[k]:
                selected_cases.append(groups[k].pop(0))
                if len(selected_cases) >= max_cases:
                    break
            if groups[k]:
                next_active_keys.append(k)
        active_keys = next_active_keys

    # Coverage metrics
    covered_tools = sorted(list({c.tool_id for c in selected_cases}))
    covered_families = sorted(
        list({c.fault_family for c in selected_cases}), key=lambda f: f.value
    )

    counters = GenerationCounters(
        examined_candidates=examined_count,
        statically_valid_candidates=valid_count,
        rejected_candidates=rejected_count,
        semantic_duplicates=duplicate_count,
        unique_valid_candidates=len(unique_candidates),
        selected_cases=len(selected_cases),
    )

    coverage_notes = []
    if is_truncated:
        coverage_notes.append(
            f"Candidate enumeration was truncated upon reaching examination budget of {max_budget}."
        )
    coverage_notes.append(
        f"Selected {len(selected_cases)} cases across {len(covered_families)} fault families and {len(covered_tools)} tools."
    )

    coverage = CoverageSummary(
        fault_families_eligible=sorted(list(eligible_families), key=lambda f: f.value),
        fault_families_covered=covered_families,
        tools_eligible=sorted(list(eligible_tools)),
        tools_covered=covered_tools,
        candidate_population_denominator=examined_count if not is_truncated else None,
        is_truncated=is_truncated,
        notes=coverage_notes,
    )

    # 6. Determine Generation Status
    if is_truncated and not selected_cases:
        status = GenerationStatus.TRUNCATED_SEARCH
    elif selected_cases:
        status = GenerationStatus.GENERATED
    elif skipped_summaries and not unique_candidates:
        status = GenerationStatus.FILTERED_OUT
    elif rejected_summaries or not eligible_tools:
        status = GenerationStatus.INCOMPATIBLE_METADATA
    else:
        status = GenerationStatus.EMPTY_SEARCH

    # 7. Assemble Frozen Versioned Suite
    frozen_suite: FrozenSuite | None = None
    if selected_cases:
        canonical_manifests = []
        for m in sorted_manifests:
            m_dict = m.model_dump(mode="json")
            m_dict["tools"] = sorted(
                m_dict.get("tools", []), key=lambda t: t.get("tool_id", "")
            )
            m_dict["capabilities"] = sorted(
                m_dict.get("capabilities", []),
                key=lambda c: (
                    c.get("fault_family", ""),
                    c.get("effect_phase", ""),
                    c.get("hook", ""),
                    c.get("tool_id") or "",
                ),
            )
            canonical_manifests.append(m_dict)

        canonical_rcs = []
        for r in sorted_contracts:
            r_dict = r.model_dump(mode="json")
            r_dict["permitted_terminal_outcomes"] = sorted(
                r_dict.get("permitted_terminal_outcomes", [])
            )
            r_dict["graceful_stopping_conditions"] = sorted(
                r_dict.get("graceful_stopping_conditions", [])
            )
            r_dict["required_assertion_ids"] = sorted(
                r_dict.get("required_assertion_ids", [])
            )
            r_dict["rule_ids"] = sorted(r_dict.get("rule_ids", []))
            canonical_rcs.append(r_dict)

        filters_dict = None
        if request.filters:
            filters_dict = {
                "tool_ids": (
                    sorted(request.filters.tool_ids)
                    if request.filters.tool_ids
                    else None
                ),
                "fault_families": (
                    sorted([f.value for f in request.filters.fault_families])
                    if request.filters.fault_families
                    else None
                ),
                "effect_phases": (
                    sorted([p.value for p in request.filters.effect_phases])
                    if request.filters.effect_phases
                    else None
                ),
            }

        input_snapshots = {
            "tasks": [t.model_dump(mode="json") for t in sorted_tasks],
            "adapter_manifests": canonical_manifests,
            "fixtures": [f.model_dump(mode="json") for f in sorted_fixtures],
            "recovery_contracts": canonical_rcs,
            "filters": filters_dict,
        }

        case_fps = {
            c.case_id: compute_case_semantic_fingerprint(c) for c in selected_cases
        }
        case_fams = {
            c.case_id: candidate_case_families[c.case_id] for c in selected_cases
        }
        selected_rcs = {
            c.recovery_contract_id: candidate_recovery_contracts[c.recovery_contract_id]
            for c in selected_cases
            if c.recovery_contract_id in candidate_recovery_contracts
        }

        pending_checks = [
            "Runtime adapter tool endpoint and protocol verification pending.",
            "Runtime fault injector delivery for catalogue family pending.",
            "Agent invocation and recovery evaluation pending.",
        ]
        limitations = [
            "Static candidate generation only; cases are not executed or verified at runtime.",
            "Clean control qualification and fault exposure require live runtime execution.",
            "Recovery verdict is strictly null.",
        ]

        suite_payload = {
            "schema_version": "1.0.0",
            "generator_version": "1.0.0",
            "suite_id": "suite-placeholder",
            "project_id": request.project_id,
            "seed": request.seed,
            "policy": request.policy.model_dump(mode="json"),
            "input_snapshots": input_snapshots,
            "cases": [c.model_dump(mode="json") for c in selected_cases],
            "case_fingerprints": case_fps,
            "case_families": case_fams,
            "recovery_contracts": {
                k: v.model_dump(mode="json") for k, v in selected_rcs.items()
            },
            "counters": counters.model_dump(mode="json"),
            "truncated": is_truncated,
            "static_validation_status": ValidationStatus.STATIC_VALID.value,
            "pending_checks": pending_checks,
            "limitations": limitations,
        }

        content_digest = compute_suite_content_digest(suite_payload)
        suite_id = f"suite-{content_digest[:16]}"
        suite_payload["suite_id"] = suite_id
        suite_payload["content_digest"] = content_digest
        suite_payload["created_at_utc"] = datetime.now(timezone.utc).isoformat()

        frozen_suite = FrozenSuite.model_validate(suite_payload)

    pending_runtime_checks = [
        "Runtime adapter tool endpoints and schemas unverified.",
        "Runtime fault injector delivery for non-timeout families not yet implemented.",
        "Agent invocation protocol and recovery evaluation deferred.",
    ]

    return CaseGenerationResponse(
        validation_scope=ValidationScope.STATIC_ONLY,
        status=status,
        project_id=request.project_id,
        selected_cases=selected_cases,
        frozen_suite=frozen_suite,
        counters=counters,
        rejected_summaries=rejected_summaries[:20],
        skipped_summaries=skipped_summaries[:20],
        coverage_summary=coverage,
        pending_checks=pending_runtime_checks,
        runtime_verified=False,
        execution_ready=False,
        recovery_verdict=None,
    )

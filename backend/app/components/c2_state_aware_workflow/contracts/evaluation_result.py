"""Evaluation result contract for Component 2: State-Aware Multi-Step Workflow Testing.

Captures the verdict, standard reason codes, pinned model/test versions, expected
and observed state sequences, detailed violations, first-divergence localisation,
evidence references, coverage measures, and evaluator execution timing.

CRITICAL REQUIREMENT:
Restricted strictly to the exact six verdicts defined in the research proposal:
- PASS
- EXPECTED REJECTION PASS
- FAIL
- INCONCLUSIVE
- MODEL NOT READY
- TEST NOT READY
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from app.components.c2_state_aware_workflow.contracts.enums import (
    EvaluationVerdict,
    ReasonCode,
)


class WorkflowViolation(BaseModel):
    """Specific rule, transition, or invariant violation identified during conformance checking."""

    model_config = ConfigDict(extra="forbid")

    step_index: int = Field(
        ..., ge=0, description="Sequence index where violation occurred"
    )
    violation_type: str = Field(
        ...,
        description="Type: 'TRANSITION_NOT_ENABLED', 'GUARD_FAILED', 'INVARIANT_BROKEN', "
        "'ENTITY_CONTINUITY_BROKEN', 'EXPECTED_EFFECT_MISSING', 'PROTECTED_FIELD_MODIFIED'",
    )
    rule_id: str | None = Field(
        default=None,
        description="Associated rule, transition, or invariant ID",
    )
    description: str = Field(
        ..., description="Human-readable explanation of the defect"
    )
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Detailed diagnostic attributes (e.g. expected vs observed values)",
    )


class FirstDivergenceInfo(BaseModel):
    """Localisation record identifying the earliest point of workflow non-conformance.

    Per proposal definition:
    'For a trace with observations indexed by i, the first-divergence index is the
    smallest i for which no enabled transition in any accepted model path can
    explain the observed event and state effect.'
    """

    model_config = ConfigDict(extra="forbid")

    first_divergence_index: int = Field(
        ...,
        ge=0,
        description="Smallest observation index i where execution deviated from the EFSM oracle",
    )
    expected_transition: str | None = Field(
        default=None,
        description="Transition ID that was expected to fire at this step",
    )
    expected_state: str | None = Field(
        default=None,
        description="Expected state before or after this step",
    )
    observed_event: str | None = Field(
        default=None,
        description="Event name observed at the divergence step",
    )
    observed_state: str | None = Field(
        default=None,
        description="Observed state resulting from the divergent event",
    )
    reason: str = Field(
        ...,
        description="Explicit explanation of why no valid model path could accept this step",
    )


class WorkflowCoverageInfo(BaseModel):
    """Workflow model coverage metrics achieved during test execution."""

    model_config = ConfigDict(extra="forbid")

    transitions_covered: list[str] = Field(
        default_factory=list,
        description="List of unique transition IDs successfully exercised",
    )
    transitions_total: int = Field(
        default=0,
        ge=0,
        description="Total reachable transitions declared in reference model",
    )
    transition_coverage_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Ratio of transitions exercised (>= 0.80 target)",
    )
    guards_covered: list[str] = Field(
        default_factory=list,
        description="List of guard conditions exercised with true/false evaluations",
    )
    guards_total: int = Field(
        default=0,
        ge=0,
        description="Total distinct guard condition outcomes declared",
    )
    guard_coverage_ratio: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Ratio of guard outcomes evaluated (>= 0.75 target)",
    )
    paths_covered: list[str] = Field(
        default_factory=list,
        description="Identifiers of target reference paths completed",
    )
    state_effects_detected: int = Field(
        default=0,
        ge=0,
        description="Count of state effect mutations verified",
    )


class WorkflowEvaluationResult(BaseModel):
    """Complete evaluation result contract for Component 2.

    Note: Defining this contract does NOT mean the evaluator is implemented in Phase 1.
    All fields are typed and versioned to establish the boundary.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: EvaluationVerdict = Field(
        ...,
        description="One of the exact six verdicts mandated by the proposal",
    )
    reason_codes: list[ReasonCode] = Field(
        default_factory=list,
        description="Machine-readable reason codes explaining verdict",
    )
    model_id: str = Field(..., description="Pinned reference EFSM model identifier")
    model_version: str = Field(..., description="Pinned reference EFSM version string")
    test_id: str = Field(..., description="Pinned generated test identifier")
    test_version: str = Field(..., description="Pinned generated test version string")
    expected_state_sequence: list[str] = Field(
        ...,
        description="Expected sequence of states from reference model",
    )
    observed_state_sequence: list[str] = Field(
        ...,
        description="Observed sequence of states derived from runtime trace",
    )
    violations: list[WorkflowViolation] = Field(
        default_factory=list,
        description="Itemized violations detected during trace alignment",
    )
    first_divergence: FirstDivergenceInfo | None = Field(
        default=None,
        description="Localisation of earliest divergence step, if verdict is FAIL",
    )
    evidence_references: list[str] = Field(
        default_factory=list,
        description="List of event IDs or trace UUIDs cited as supporting evidence",
    )
    coverage: WorkflowCoverageInfo = Field(
        default_factory=WorkflowCoverageInfo,
        description="Coverage contribution achieved by this execution",
    )
    evaluated_at: datetime = Field(
        ...,
        description="Timestamp when the evaluation was computed",
    )
    evaluation_duration_ms: float = Field(
        ...,
        ge=0.0,
        description="Execution duration of the evaluator in milliseconds",
    )

"""C4 Evaluation findings, verdict types, and violation stages."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from app.components.c4_policy_aware_safety.contracts.sources import SourceReference


class PolicyVerdict(str, Enum):
    """C4 deterministic evaluation verdicts."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_EXERCISED = "NOT_EXERCISED"


class ViolationStage(str, Enum):
    """Specific stage where a policy boundary violation occurred."""

    ATTEMPTED_PROHIBITED_ACTION = "ATTEMPTED_PROHIBITED_ACTION"
    COMPLETED_PROHIBITED_ACTION = "COMPLETED_PROHIBITED_ACTION"
    PROTECTED_INFO_DISCLOSURE = "PROTECTED_INFO_DISCLOSURE"
    INSTRUCTION_AUTHORITY_VIOLATION = "INSTRUCTION_AUTHORITY_VIOLATION"


class ReasonCode(str, Enum):
    """Granular machine-readable rationale for evaluation verdicts."""

    AUTHORIZED_ACTION_COMPLIANT = "AUTHORIZED_ACTION_COMPLIANT"
    PROHIBITED_ACTION_ATTEMPTED = "PROHIBITED_ACTION_ATTEMPTED"
    PROHIBITED_ACTION_COMMITTED = "PROHIBITED_ACTION_COMMITTED"
    PROHIBITED_DISCLOSURE_OBSERVED = "PROHIBITED_DISCLOSURE_OBSERVED"
    INSTRUCTION_AUTHORITY_COMPROMISED = "INSTRUCTION_AUTHORITY_COMPROMISED"
    MISSING_REQUIRED_EVIDENCE = "MISSING_REQUIRED_EVIDENCE"
    INCOMPLETE_TRACE = "INCOMPLETE_TRACE"
    BOUNDARY_NOT_EXERCISED = "BOUNDARY_NOT_EXERCISED"
    ATTACK_NOT_EXPOSED = "ATTACK_NOT_EXPOSED"
    ATTACK_EXPOSURE_UNKNOWN = "ATTACK_EXPOSURE_UNKNOWN"
    RULE_NOT_APPLICABLE = "RULE_NOT_APPLICABLE"
    BACKEND_BLOCKED_ATTEMPT = "BACKEND_BLOCKED_ATTEMPT"


class Severity(str, Enum):
    """Severity classification for policy rules and violations."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvaluationFinding(BaseModel):
    """Detailed deterministic policy evaluation result for a single rule."""

    component_id: str = Field(default="C4", description="Research component identifier")
    finding_id: str = Field(..., description="Unique finding ID")
    project_id: str = Field(..., description="Project ID")
    case_id: str | None = Field(default=None, description="Optional test case ID")
    run_id: str | None = Field(default=None, description="Optional execution run ID")
    contract_id: str = Field(..., description="Evaluated policy contract ID")
    contract_version: int = Field(..., description="Evaluated policy contract version")
    rule_id: str = Field(..., description="Evaluated policy rule ID")
    rule_version: int = Field(..., description="Evaluated policy rule version")
    verdict: PolicyVerdict = Field(..., description="C4 verdict")
    reason_codes: list[ReasonCode] = Field(..., min_length=1)
    severity: Severity = Field(..., description="Rule severity")
    source_policy_reference: SourceReference = Field(
        ..., description="Supporting source reference"
    )
    supporting_evidence_ids: list[str] = Field(
        default_factory=list,
        description="IDs of runtime evidence events supporting this verdict",
    )
    violation_stage: ViolationStage | None = Field(
        default=None,
        description="Violation stage if verdict is FAIL; None otherwise",
    )
    missing_evidence_list: list[str] = Field(
        default_factory=list,
        description="Names of required evidence elements missing during evaluation",
    )
    observed_effect: dict[str, Any] | None = Field(
        default=None,
        description="Observed state changes or backend rejection observations",
    )
    attacker_goal_achieved: bool | None = Field(
        default=None,
        description="Attacker goal success reported separately from policy verdict",
    )
    causal_attribution: str = Field(
        default="UNKNOWN",
        description="Causal attribution: PROVEN, UNPROVEN, or UNKNOWN",
    )
    explanation: str = Field(..., description="Concise human-readable rationale")


class BenignUtilityResult(BaseModel):
    """Tracking of benign task completion, decoupled from policy verdicts."""

    task_completed: bool | None = Field(
        default=None,
        description="True if legitimate task was achieved, False if failed, None if unknown",
    )
    details: str | None = Field(default=None)


class C4EvaluationReport(BaseModel):
    """Overall evaluation output bundling per-rule findings and metadata."""

    project_id: str = Field(...)
    case_id: str | None = Field(default=None)
    run_id: str | None = Field(default=None)
    contract_id: str = Field(...)
    contract_version: int = Field(...)
    aggregate_verdict: PolicyVerdict = Field(...)
    findings: list[EvaluationFinding] = Field(default_factory=list)
    benign_utility: BenignUtilityResult = Field(default_factory=BenignUtilityResult)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

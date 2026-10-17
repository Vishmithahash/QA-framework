"""Validation contracts and readiness report schemas for Component 2."""

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from app.components.c2_state_aware_workflow.contracts.enums import (
    EvaluationVerdict,
    ReasonCode,
    ValidationSeverity,
)


class ValidationIssue(BaseModel):
    """Specific error, warning, or assumption identified during model validation."""

    model_config = ConfigDict(extra="forbid")

    issue_code: str = Field(..., description="Machine-readable issue code")
    severity: ValidationSeverity = Field(
        ..., description="Severity level: ERROR, WARNING, or ASSUMPTION"
    )
    message: str = Field(..., description="Short summary of the validation finding")
    affected_element_type: str = Field(
        ...,
        description="Type of element: 'state', 'transition', 'variable', 'invariant', 'milestone', 'rule', 'field', 'model'",
    )
    affected_element_id: str | None = Field(
        default=None,
        description="Identifier of the specific state, transition, or rule affected",
    )
    explanation: str = Field(
        ...,
        description="Detailed explanation of the defect, implication, or assumption",
    )
    is_blocking: bool = Field(
        default=True,
        description="True if this issue blocks approval and usage as reference oracle",
    )


class ValidationReport(BaseModel):
    """Structured validation report recording reference model correctness evidence."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(..., description="Target reference model ID")
    version: str = Field(..., description="Target model version")
    project_id: str = Field(..., description="Associated project identifier")
    definition_hash: str = Field(
        ..., description="Canonical SHA-256 hash of the exact validated definition"
    )
    validator_version: str = Field(
        default="2.0.0", description="Version of the model validator engine"
    )
    validation_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Validator configuration, domain bounds, and resource limits applied",
    )
    is_valid: bool = Field(
        ...,
        description="True if model satisfies all structural and bounded semantic checks without blocking errors",
    )
    has_blocking_issues: bool = Field(
        ...,
        description="True if any blocking errors prevent approval or test generation",
    )
    checks_performed: list[str] = Field(
        default_factory=list,
        description="List of specific validation checks successfully executed",
    )
    checks_not_completed: list[dict[str, str]] = Field(
        default_factory=list,
        description="Checks omitted due to finite domain limits, resource bounds, or unsupported properties",
    )
    errors: list[ValidationIssue] = Field(
        default_factory=list,
        description="Critical defects preventing model validation and approval",
    )
    warnings: list[ValidationIssue] = Field(
        default_factory=list,
        description="Potential issues, permitted non-determinism, or review recommendations",
    )
    unresolved_assumptions: list[ValidationIssue] = Field(
        default_factory=list,
        description="Explicit synthetic or domain assumptions requiring human review",
    )
    validated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when validation was executed",
    )


class ModelReadinessInfo(BaseModel):
    """Model readiness assessment for test generation and runtime alignment phases."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="Project identifier")
    model_id: str = Field(..., description="Workflow model ID")
    version: str = Field(..., description="Model version")
    is_ready: bool = Field(
        ...,
        description="True if reference model is validated, approved, and fully usable",
    )
    status: str = Field(..., description="'READY' or 'MODEL_NOT_READY'")
    verdict: EvaluationVerdict | None = Field(
        default=None,
        description="Set to MODEL_NOT_READY when model is not ready. Never set to PASS for model validation.",
    )
    reasons: list[ReasonCode] = Field(
        default_factory=list,
        description="Reason codes explaining why the model is NOT READY",
    )
    explanation: str = Field(
        ..., description="Detailed explanation of current readiness or non-readiness"
    )

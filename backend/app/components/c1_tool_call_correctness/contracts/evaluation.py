"""Evaluation verdict, individual check outcome, and diagnosis contracts (FR-06/FR-07/FR-08)."""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field

from .base import (
    CheckStatus,
    CheckType,
    DiagnosisClassification,
    EvaluationVerdict,
    SourceRelationStatus,
)


class ReasonCode(str, Enum):
    """Stable reason codes explaining check outcomes and failures (FR-07)."""

    MATCH_EXACT = "MATCH_EXACT"
    TOOL_NOT_PERMITTED = "TOOL_NOT_PERMITTED"
    MANDATORY_TOOL_OMITTED = "MANDATORY_TOOL_OMITTED"
    TOOL_CALL_OUT_OF_ORDER = "TOOL_CALL_OUT_OF_ORDER"
    ARGUMENT_MISSING = "ARGUMENT_MISSING"
    UNEXPECTED_ARGUMENT = "UNEXPECTED_ARGUMENT"
    ARGUMENT_TYPE_MISMATCH = "ARGUMENT_TYPE_MISMATCH"
    ARGUMENT_VALUE_MISMATCH = "ARGUMENT_VALUE_MISMATCH"
    MALFORMED_ARGUMENTS_PAYLOAD = "MALFORMED_ARGUMENTS_PAYLOAD"
    REQUIRED_ARGUMENT_SOURCE_UNPROVEN = "REQUIRED_ARGUMENT_SOURCE_UNPROVEN"
    EVIDENCE_MISSING_FOR_MANDATORY_CHECK = "EVIDENCE_MISSING_FOR_MANDATORY_CHECK"
    EXECUTION_INTERRUPTED = "EXECUTION_INTERRUPTED"
    TOOL_RUNTIME_EXCEPTION = "TOOL_RUNTIME_EXCEPTION"
    UNKNOWN_REASON = "UNKNOWN_REASON"


class CheckOutcome(BaseModel):
    """Evaluation result for an atomic tool selection or argument check (FR-05)."""

    check_id: str = Field(..., description="Unique check identifier")
    check_type: CheckType = Field(..., description="Category of correctness check")
    status: CheckStatus = Field(..., description="Outcome of the individual check")
    tool_name: Optional[str] = Field(default=None, description="Tool name evaluated")
    parameter_name: Optional[str] = Field(
        default=None, description="Argument parameter evaluated"
    )
    requirement_refs: list[str] = Field(
        default_factory=list,
        description="Associated requirements justifying this check",
    )
    evidence_refs: list[str] = Field(
        default_factory=list,
        description="Trace events or telemetry supporting the check outcome",
    )
    expected_value: Any = Field(
        default=None, description="Expected value or constraint pattern"
    )
    observed_value: Any = Field(
        default=None, description="Observed value extracted from trace"
    )
    reason_code: ReasonCode = Field(
        default=ReasonCode.UNKNOWN_REASON,
        description="Stable code explaining the check verdict",
    )
    message: str = Field(
        default="", description="Human-readable explanation of check outcome"
    )
    source_relation_status: SourceRelationStatus = Field(
        default=SourceRelationStatus.UNKNOWN,
        description="Whether parameter source relationship was OBSERVED, INFERRED, or UNKNOWN",
    )

    model_config = {"extra": "forbid"}


class DiagnosisResult(BaseModel):
    """Root-cause classification and code defect localization (FR-08).

    Code-location findings require supporting evidence and available source access.
    Lack of source access makes code diagnosis unavailable, but does not block correctness evaluation.
    """

    diagnosis_id: str = Field(..., description="Unique diagnosis identifier")
    classification: DiagnosisClassification = Field(
        ...,
        description="Defect classification (SUPPORTED_CODE_DEFECT, AGENT_BEHAVIOUR, etc.)",
    )
    confidence_score: Optional[float] = Field(
        default=None,
        description="Confidence score [0.0 - 1.0] for the diagnosis",
    )
    failing_call_id: Optional[str] = Field(
        default=None,
        description="Identifier of the specific tool invocation manifesting the defect",
    )
    suspected_symbol: Optional[str] = Field(
        default=None,
        description="Name of function, method, or schema symbol suspected of code defect",
    )
    suspected_file_path: Optional[str] = Field(
        default=None,
        description="Relative file path of suspected source code defect",
    )
    line_number: Optional[int] = Field(
        default=None,
        description="Line number where defect is localized",
    )
    explanation: str = Field(
        default="",
        description="Explainable chain linking observed failure to diagnosis",
    )
    evidence_references: list[str] = Field(
        default_factory=list,
        description="Trace events and source code AST findings supporting diagnosis",
    )

    model_config = {"extra": "forbid"}


class EvaluationResult(BaseModel):
    """Comprehensive C1 evaluation result for a single test case trial (FR-06/FR-07)."""

    evaluation_id: str = Field(..., description="Unique evaluation identifier")
    project_id: str = Field(..., description="Project identifier")
    case_id: str = Field(..., description="Test case identifier")
    run_id: str = Field(..., description="Execution run identifier")
    verdict: EvaluationVerdict = Field(
        ...,
        description="Overall verdict (PASS, FAIL, INCONCLUSIVE)",
    )
    checks: list[CheckOutcome] = Field(
        default_factory=list,
        description="List of all atomic correctness checks evaluated",
    )
    failing_call_id: Optional[str] = Field(
        default=None,
        description="Reference to primary failing call if verdict is FAIL",
    )
    diagnosis: Optional[DiagnosisResult] = Field(
        default=None,
        description="Root cause diagnosis if verdict is FAIL and diagnosis is eligible",
    )
    evaluator_version: str = Field(
        default="1.0.0",
        description="Version string of the C1 evaluator engine",
    )
    summary_explanation: str = Field(
        default="",
        description="High-level explanation of verdict against requirements (FR-07)",
    )

    model_config = {"extra": "forbid"}

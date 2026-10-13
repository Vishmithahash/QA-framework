"""Candidate test case and structured assertion contracts (FR-02/FR-03)."""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field

from .base import CaseReadiness


class ConstraintType(str, Enum):
    """Supported types of expected argument value sources."""

    LITERAL = "LITERAL"
    FIXTURE_FACT = "FIXTURE_FACT"
    SESSION_FACT = "SESSION_FACT"
    TOOL_OUTPUT_REF = "TOOL_OUTPUT_REF"
    UNSUPPORTED = "UNSUPPORTED"


class ConstraintOperator(str, Enum):
    """Comparison operators for structured argument assertions."""

    EQUALS = "EQUALS"
    CONTAINS = "CONTAINS"
    IN_SET = "IN_SET"
    IS_NULL = "IS_NULL"
    NOT_NULL = "NOT_NULL"


class ValueConstraint(BaseModel):
    """Structured constraint for an expected argument value.

    Arbitrary code, shell commands, SQL, and eval expressions are strictly prohibited.
    Values must originate from literals or verified system facts.
    """

    constraint_type: ConstraintType = Field(
        ...,
        description="Source of the expected value (LITERAL, FIXTURE_FACT, SESSION_FACT, etc.)",
    )
    operator: ConstraintOperator = Field(
        default=ConstraintOperator.EQUALS,
        description="Comparison operator to apply against observed argument",
    )
    literal_value: Optional[Any] = Field(
        default=None,
        description="Constant value when constraint_type is LITERAL",
    )
    reference_path: Optional[str] = Field(
        default=None,
        description="Path or key when constraint_type is FIXTURE_FACT or SESSION_FACT (e.g. 'users.0.id')",
    )
    source_call_id: Optional[str] = Field(
        default=None,
        description="Prior tool call identifier when constraint_type is TOOL_OUTPUT_REF",
    )
    raw_expression: Optional[str] = Field(
        default=None,
        description="Raw input preserved when an unsupported expression form was attempted",
    )

    model_config = {"extra": "forbid"}


class ExpectedCallConstraint(BaseModel):
    """Structured expectation of a tool call required by the task (FR-03/FR-05)."""

    call_key: str = Field(
        ..., description="Unique label for this expected call in the test case"
    )
    tool_name: str = Field(..., description="Expected tool name to be invoked")
    tool_id: Optional[str] = Field(
        default=None, description="Optional tool ID reference"
    )
    is_required: bool = Field(
        default=True, description="Whether this tool invocation is strictly mandatory"
    )
    order_index: Optional[int] = Field(
        default=None, description="Expected relative order in multi-call sequences"
    )
    argument_constraints: dict[str, ValueConstraint] = Field(
        default_factory=dict,
        description="Map of parameter names to their structured ValueConstraints",
    )
    requirement_refs: list[str] = Field(
        default_factory=list,
        description="Requirements mandating this specific tool call or parameters",
    )

    model_config = {"extra": "forbid"}


class ValidationIssue(BaseModel):
    """Structured issue produced by C1 validation services."""

    code: str = Field(..., description="Stable machine-readable error code")
    field_path: str = Field(
        ..., description="Dot-separated path to the problematic field or entity"
    )
    message: str = Field(
        ..., description="Human-readable explanation of the validation failure"
    )
    severity: str = Field(
        default="ERROR", description="Severity level ('ERROR' or 'WARNING')"
    )

    model_config = {"extra": "forbid"}


class CandidateTestCase(BaseModel):
    """Candidate test case specification prior to execution (FR-02/FR-03).

    If validation issues are present, readiness is NOT_READY and the case is
    excluded from evaluation scoring. It is never counted as an agent failure.
    """

    case_id: str = Field(
        ..., description="Unique test case identifier (e.g. 'TC-C1-001')"
    )
    project_id: str = Field(..., description="Associated project identifier")
    task_prompt: str = Field(
        ..., description="Natural language prompt presented to the agent under test"
    )
    fixture_refs: list[str] = Field(
        default_factory=list,
        description="Required data fixture identifiers needed to set up clean environment",
    )
    requirement_versions: dict[str, str] = Field(
        default_factory=dict,
        description="Map of requirement IDs to their pinned version strings",
    )
    tool_versions: dict[str, str] = Field(
        default_factory=dict,
        description="Map of tool names/IDs to their pinned version strings",
    )
    expected_calls: list[ExpectedCallConstraint] = Field(
        default_factory=list,
        description="Structured expectations of tool calls and parameters",
    )
    required_evidence_refs: list[str] = Field(
        default_factory=list,
        description="References to telemetry/logs required to verify the run",
    )
    readiness: CaseReadiness = Field(
        default=CaseReadiness.NOT_READY,
        description="Whether this case passed validation and is eligible for execution",
    )
    validation_issues: list[ValidationIssue] = Field(
        default_factory=list,
        description="List of issues preventing this candidate from reaching READY state",
    )

    model_config = {"extra": "forbid"}

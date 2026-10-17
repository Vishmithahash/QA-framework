"""Validation issue contracts for candidate rules and contracts."""

from enum import Enum
from pydantic import BaseModel, Field


class IssueCode(str, Enum):
    """Categorization of policy candidate and contract validation issues."""

    AMBIGUOUS = "AMBIGUOUS"
    UNSUPPORTED = "UNSUPPORTED"
    CONFLICTING = "CONFLICTING"
    MISSING_SOURCE = "MISSING_SOURCE"
    INVALID_REFERENCE = "INVALID_REFERENCE"


class CandidateValidationIssue(BaseModel):
    """Structured issue identifying an unresolvable defect or ambiguity in a candidate rule."""

    code: IssueCode = Field(..., description="Category code of validation issue")
    message: str = Field(..., description="Human-readable explanation of the issue")
    rule_id: str | None = Field(
        default=None, description="Affected rule ID if rule-specific"
    )
    field: str | None = Field(
        default=None, description="Specific field path where issue was found"
    )
    blocking: bool = Field(
        default=True,
        description="Whether this issue blocks contract acceptance (True prevents acceptance)",
    )

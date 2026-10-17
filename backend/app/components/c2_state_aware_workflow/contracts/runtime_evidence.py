"""Runtime evidence contract for Component 2.

Captures ordered runtime execution events, tool calls, entity identifiers,
before-and-after system state observations, state differences, and evidence
completeness tracking.

CRITICAL REQUIREMENT:
Distinguishes missing evidence from explicit null values.
"""

from datetime import datetime
from typing import Any, Self
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.components.c2_state_aware_workflow.contracts.enums import EvidencePresence


class ObservedValue(BaseModel):
    """Represents an observed system variable or attribute.

    Explicitly differentiates between:
    - PRESENT: An observation was captured and has a non-null value (or boolean/zero).
    - EXPLICIT_NULL: The field was inspected in the system/database and is confirmed
      to be None/NULL (e.g. refund_id is null before refund request).
    - MISSING: No observation could be captured (query timed out, field unobserved,
      or observation collector skipped this attribute).
    """

    model_config = ConfigDict(extra="forbid")

    value: Any = Field(default=None, description="Observed value, if present")
    presence: EvidencePresence = Field(
        ...,
        description="PRESENT, EXPLICIT_NULL, or MISSING",
    )

    @model_validator(mode="after")
    def validate_presence_consistency(self) -> Self:
        if self.presence == EvidencePresence.PRESENT and self.value is None:
            raise ValueError(
                "ObservedValue with presence=PRESENT must contain a non-null value. "
                "Use EXPLICIT_NULL if the system attribute is actually None/null."
            )
        if (
            self.presence in (EvidencePresence.EXPLICIT_NULL, EvidencePresence.MISSING)
            and self.value is not None
        ):
            raise ValueError(
                f"ObservedValue with presence={self.presence.value} must have value=None."
            )
        return self

    @classmethod
    def of(cls, val: Any) -> "ObservedValue":
        """Factory for a present, non-null value."""
        if val is None:
            return cls(value=None, presence=EvidencePresence.EXPLICIT_NULL)
        return cls(value=val, presence=EvidencePresence.PRESENT)

    @classmethod
    def explicit_null(cls) -> "ObservedValue":
        """Factory for an inspected field that is confirmed null."""
        return cls(value=None, presence=EvidencePresence.EXPLICIT_NULL)

    @classmethod
    def missing(cls) -> "ObservedValue":
        """Factory for uncaptured or unavailable evidence."""
        return cls(value=None, presence=EvidencePresence.MISSING)

    @property
    def is_present(self) -> bool:
        return self.presence == EvidencePresence.PRESENT

    @property
    def is_explicit_null(self) -> bool:
        return self.presence == EvidencePresence.EXPLICIT_NULL

    @property
    def is_missing(self) -> bool:
        return self.presence == EvidencePresence.MISSING


class EvidenceCompletenessInfo(BaseModel):
    """Tracks completeness of evidence captured during an execution step."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(
        ...,
        description="'COMPLETE', 'PARTIAL', or 'MISSING'",
    )
    missing_evidence_fields: list[str] = Field(
        default_factory=list,
        description="List of fields that were expected but could not be captured",
    )
    is_complete: bool = Field(
        ...,
        description="True only if all required observations were captured without gaps",
    )
    notes: str | None = Field(
        default=None,
        description="Contextual notes regarding observation collection",
    )


class RuntimeEvidenceEvent(BaseModel):
    """A single ordered event captured during agent execution."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="Project identifier")
    run_id: str = Field(..., description="Execution run identifier")
    test_id: str = Field(..., description="Test case identifier")
    event_id: str = Field(..., description="Unique event identifier")
    sequence_index: int = Field(
        ...,
        ge=0,
        description="Logical zero-indexed sequence number of this event in the run",
    )
    tool_call_id: str | None = Field(
        default=None,
        description="Correlation ID of the tool call if event originated from a tool execution",
    )
    timestamp: datetime = Field(
        ...,
        description="UTC timestamp when the event was recorded",
    )
    tool_name: str = Field(
        ..., description="Name of the tool invoked, e.g. 'get_orders'"
    )
    tool_input: dict[str, Any] = Field(
        default_factory=dict,
        description="Input parameters provided to the tool by the agent",
    )
    tool_output: Any = Field(
        default=None,
        description="Return value or response payload from the tool invocation",
    )
    error: str | None = Field(
        default=None,
        description="Error message if tool execution failed or threw an exception",
    )
    entity_ids: dict[str, Any] = Field(
        default_factory=dict,
        description="Entity keys observed in this event, e.g. {'customer_id': 42, 'order_id': 503}",
    )
    before_state: dict[str, ObservedValue] = Field(
        default_factory=dict,
        description="State observation captured before tool execution",
    )
    after_state: dict[str, ObservedValue] = Field(
        default_factory=dict,
        description="State observation captured after tool execution",
    )
    state_diff: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured diff showing mutations between before_state and after_state",
    )
    evidence_completeness: EvidenceCompletenessInfo = Field(
        ...,
        description="Audit record of evidence completeness for this step",
    )


class WorkflowExecutionEvidence(BaseModel):
    """Aggregated sequence of runtime evidence events for a complete test run."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="Project identifier")
    run_id: str = Field(..., description="Execution run identifier")
    test_id: str = Field(..., description="Test case identifier")
    events: list[RuntimeEvidenceEvent] = Field(
        default_factory=list,
        description="Ordered sequence of runtime evidence events",
    )
    total_events: int = Field(..., ge=0, description="Total count of events recorded")
    captured_at: datetime = Field(
        ...,
        description="Timestamp when the trace collection was finalized",
    )

"""Runtime evidence and execution trace contracts (FR-04)."""

from typing import Any, Optional
from pydantic import BaseModel, Field

from .base import ExecutionStatus


class ObservedToolCall(BaseModel):
    """Recorded tool call observed during an agent test execution run.

    Critical semantic rule:
    Observed calls MUST remain representable even when the agent uses an unknown tool
    or passes malformed/unparseable arguments. The trace must never be rejected at intake
    merely because it contains the defect C1 is responsible for evaluating.
    """

    call_id: str = Field(..., description="Unique tool call invocation identifier")
    event_id: str = Field(
        ..., description="Correlated event identifier in shared trace system"
    )
    tool_name: str = Field(
        ..., description="Tool name called by agent (can be unknown/unregistered)"
    )
    arguments: Any = Field(
        default=None,
        description="Parsed arguments object, scalar, or raw payload if malformed",
    )
    raw_arguments: Optional[str] = Field(
        default=None,
        description="Exact raw argument string emitted by LLM agent before parsing",
    )
    is_arguments_malformed: bool = Field(
        default=False,
        description="Flag set when LLM produced invalid JSON or unparseable argument string",
    )
    is_unknown_tool: bool = Field(
        default=False,
        description="Flag set when tool name does not match any registered ToolDefinition",
    )
    output: Any = Field(
        default=None,
        description="Returned tool output payload or data",
    )
    output_is_explicit_null: bool = Field(
        default=False,
        description="True if tool explicitly returned null; False if output is missing/omitted",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if tool execution failed or threw an exception",
    )
    execution_status: ExecutionStatus = Field(
        default=ExecutionStatus.COMPLETED,
        description="Individual call execution status",
    )
    source_tags: list[str] = Field(
        default_factory=list,
        description="Source tags identifying proven origin of arguments (e.g. 'FIXTURE:users.0')",
    )
    evidence_refs: list[str] = Field(
        default_factory=list,
        description="References to telemetry, request logs, or database rows",
    )
    agent_config_ref: Optional[str] = Field(
        default=None,
        description="Reference to agent configuration and model parameters active during call",
    )
    tool_version: Optional[str] = Field(
        default=None,
        description="Tool implementation version active during execution",
    )

    model_config = {"extra": "forbid"}


class ExecutionTrace(BaseModel):
    """Complete execution trace for a single test case trial."""

    project_id: str = Field(..., description="Project identifier")
    case_id: str = Field(..., description="Candidate test case identifier")
    run_id: str = Field(..., description="Unique run/trial identifier")
    execution_status: ExecutionStatus = Field(
        default=ExecutionStatus.COMPLETED,
        description="Run execution status (COMPLETED, FAILED, TIMEOUT, INTERRUPTED)",
    )
    observed_calls: list[ObservedToolCall] = Field(
        default_factory=list,
        description="Chronological sequence of observed tool invocations",
    )
    interrupted: bool = Field(
        default=False,
        description="Whether run was halted prematurely before normal agent termination",
    )
    agent_final_response: Optional[str] = Field(
        default=None,
        description="Optional final textual response delivered by the agent to user",
    )
    environment_metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Environment metadata, seeds, or active fixture versions",
    )

    model_config = {"extra": "forbid"}


class RuntimeEvidence(BaseModel):
    """Aggregated runtime evidence package provided to C1 for evaluation."""

    trace: ExecutionTrace = Field(..., description="Agent tool call trace")
    fixture_snapshot_ref: Optional[str] = Field(
        default=None,
        description="Reference to post-execution fixture state snapshot",
    )
    captured_logs_ref: Optional[str] = Field(
        default=None,
        description="Reference to execution container / process stdout and stderr logs",
    )
    telemetry_events_ref: Optional[str] = Field(
        default=None,
        description="Reference to shared event stream transport evidence",
    )

    model_config = {"extra": "forbid"}

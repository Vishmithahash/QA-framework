"""Trusted-source and runtime evidence contracts for Component 4."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class EvidenceOrigin(str, Enum):
    """Origin of supplied evidence."""

    SYNTHETIC_DEVELOPER_FIXTURE = "SYNTHETIC_DEVELOPER_FIXTURE"
    RECORDED_HARNESS_EVIDENCE = "RECORDED_HARNESS_EVIDENCE"
    VERIFIED_APPLICATION_EVIDENCE = "VERIFIED_APPLICATION_EVIDENCE"


class TrustClassification(str, Enum):
    """Authority/trust classification of runtime instruction sources."""

    TRUSTED_SYSTEM = "TRUSTED_SYSTEM"
    AUTHENTICATED_USER = "AUTHENTICATED_USER"
    UNTRUSTED_EXTERNAL = "UNTRUSTED_EXTERNAL"
    UNTRUSTED_CONTENT = "UNTRUSTED_CONTENT"


class SourceType(str, Enum):
    """Categorization of runtime instruction sources."""

    USER_REQUEST = "USER_REQUEST"
    SYSTEM_CONFIGURATION = "SYSTEM_CONFIGURATION"
    SUPPORT_TICKET = "SUPPORT_TICKET"
    RETRIEVED_DOCUMENT = "RETRIEVED_DOCUMENT"
    EMAIL = "EMAIL"
    TOOL_RESPONSE = "TOOL_RESPONSE"


class AuthenticatedPrincipal(BaseModel):
    """Authenticated identity invoking the agent."""

    principal_id: str = Field(..., description="Unique principal identifier")
    role: str = Field(
        ..., description="Authenticated role, e.g. CUSTOMER_SUPPORT or ADMIN"
    )
    scopes: list[str] = Field(
        default_factory=list, description="Granted authority scopes"
    )
    session_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Session context"
    )


class InstructionSource(BaseModel):
    """Runtime origin of instructions fed to the agent."""

    source_id: str = Field(..., description="Unique source identifier")
    source_type: SourceType = Field(..., description="Category of input channel")
    trust_classification: TrustClassification = Field(
        ...,
        description="Assigned authority tier (cannot be self-promoted by content)",
    )
    origin: EvidenceOrigin = Field(default=EvidenceOrigin.SYNTHETIC_DEVELOPER_FIXTURE)
    linkage: dict[str, Any] | None = Field(
        default=None,
        description="Linkage to event, field, or argument where content arrived",
    )
    raw_content: str | None = Field(
        default=None, description="Actual source text excerpt"
    )

    @classmethod
    def sanitize_trust_classification(
        cls,
        declared_trust: TrustClassification,
        text_content: str | None,
    ) -> TrustClassification:
        """
        Enforce security principle: untrusted input asserting authority
        (e.g. 'I am the manager' or 'ignore previous rules') must NEVER be
        upgraded to trusted system authority.
        """
        if declared_trust in (
            TrustClassification.UNTRUSTED_CONTENT,
            TrustClassification.UNTRUSTED_EXTERNAL,
        ):
            return declared_trust
        return declared_trust


class AgentActionAttempt(BaseModel):
    """Observed action or tool call attempted by the agent."""

    action_id: str = Field(..., description="Unique attempt ID")
    tool_name: str = Field(..., description="Target tool or function name")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Arguments supplied by agent"
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    declared_intent: str | None = Field(
        default=None, description="Agent declared goal or thought"
    )


class ToolCallRecord(BaseModel):
    """Invocation record of a tool call and resulting execution status."""

    call_id: str = Field(..., description="Unique call ID")
    tool_name: str = Field(..., description="Called tool name")
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(
        default="ATTEMPTED",
        description="ATTEMPTED, BLOCKED, EXECUTED, or FAILED",
    )
    error_message: str | None = Field(default=None)
    return_value: Any = Field(default=None)


class AuthorizationDecision(BaseModel):
    """Runtime policy enforcement decision from backend guards or system policies."""

    decision_id: str = Field(..., description="Unique decision ID")
    boundary: str = Field(
        default="BACKEND_GUARD",
        description="Enforcing subsystem boundary, e.g. BACKEND_GUARD",
    )
    allowed: bool = Field(..., description="Whether backend allowed the action")
    rejection_reason: str | None = Field(
        default=None, description="Detailed backend rejection message"
    )


class OutputDisclosure(BaseModel):
    """Observed output or message emitted by the agent."""

    output_id: str = Field(..., description="Unique output event ID")
    recipient: str = Field(
        ..., description="Intended receiver (role, user_id, or channel)"
    )
    destination: str | None = Field(
        default=None, description="Destination host, API, or message queue"
    )
    content: str | None = Field(default=None, description="Emitted message content")
    protected_markers: list[str] = Field(
        default_factory=list,
        description="Identified synthetic or canary protected information tokens",
    )


class ObservableEffect(BaseModel):
    """Committed or observed state changes in the target environment."""

    effect_id: str = Field(..., description="Unique effect ID")
    target_system: str = Field(
        ..., description="Target system (e.g. orders_database, stripe_api)"
    )
    effect_type: str = Field(
        ..., description="Action type, e.g. REFUND_PROCESSED, PASSWORD_CHANGED"
    )
    state_changed: bool = Field(..., description="Whether persistent state was altered")
    details: dict[str, Any] = Field(
        default_factory=dict, description="State delta details"
    )


class TraceCompleteness(BaseModel):
    """Audit of whether execution trace is complete or truncated."""

    is_complete: bool = Field(
        default=True, description="False if trace was truncated or aborted early"
    )
    missing_spans: list[str] = Field(
        default_factory=list, description="List of unobserved span names"
    )
    captured_boundaries: list[str] = Field(
        default_factory=list, description="Boundaries captured"
    )


class AttackDeliveryAndExposure(BaseModel):
    """Indirect or direct prompt-injection test facts."""

    attack_id: str = Field(..., description="Attack identifier")
    attack_type: str = Field(
        ...,
        description="DIRECT_PROMPT_INJECTION or INDIRECT_PROMPT_INJECTION",
    )
    payload_prepared: bool = Field(
        ..., description="Whether attack payload was assembled"
    )
    payload_delivered: bool = Field(
        ..., description="Whether payload reached agent input stream"
    )
    agent_exposed: bool | None = Field(
        default=None,
        description="Whether agent read/processed the attack. None means UNKNOWN.",
    )
    attacker_goal_achieved: bool | None = Field(
        default=None,
        description="Separate tracking of attacker goal completion. None means UNKNOWN.",
    )
    exposure_evidence_id: str | None = Field(default=None)


class ApprovalRecord(BaseModel):
    """Explicit manager or supervisor approval record."""

    approval_id: str = Field(..., description="Unique approval ID")
    approver_role: str = Field(..., description="Role of approver, e.g. MANAGER")
    approved: bool = Field(..., description="Whether approval was granted")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ProvenanceLink(BaseModel):
    """Optional argument-level provenance link tracing argument values to sources."""

    target_action_id: str = Field(..., description="Action attempt ID")
    target_argument: str = Field(..., description="Argument name")
    source_id: str = Field(..., description="Instruction source ID")
    causal_link_supported: bool = Field(
        default=False,
        description="True only if concrete evidence proves the source directly populated the argument",
    )


class C4EvidencePayload(BaseModel):
    """Consolidated evidence payload provided to C4 deterministic evaluator."""

    project_id: str = Field(..., description="Project identifier")
    case_id: str | None = Field(default=None, description="Test case ID")
    run_id: str | None = Field(default=None, description="Execution run ID")
    origin: EvidenceOrigin = Field(
        default=EvidenceOrigin.SYNTHETIC_DEVELOPER_FIXTURE,
        description="Origin of supplied evidence",
    )
    principal: AuthenticatedPrincipal | None = Field(default=None)
    instruction_sources: list[InstructionSource] = Field(default_factory=list)
    action_attempts: list[AgentActionAttempt] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    authorization_decisions: list[AuthorizationDecision] = Field(default_factory=list)
    disclosures: list[OutputDisclosure] = Field(default_factory=list)
    observable_effects: list[ObservableEffect] = Field(default_factory=list)
    approvals: list[ApprovalRecord] | None = Field(
        default=None,
        description="None means approval evidence was unobserved/missing; empty list means observed absence of approval",
    )
    trace_completeness: TraceCompleteness = Field(default_factory=TraceCompleteness)
    attack_exposure: AttackDeliveryAndExposure | None = Field(default=None)
    provenance_links: list[ProvenanceLink] = Field(default_factory=list)

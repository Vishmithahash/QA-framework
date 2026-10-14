"""Domain and capability binding contracts for Component 4 Phase 2.

Provides application facts, schemas, role definitions, synthetic fixtures,
and injection surfaces required for automated offline test generation.
Bindings do NOT override accepted policies or specify pre-written case outcomes.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from app.components.c4_policy_aware_safety.contracts.evidence import (
    SourceType,
    TrustClassification,
)


class FieldDataType(str, Enum):
    """Primitive or policy-relevant data type."""

    INTEGER = "integer"
    MONEY_CENTS = "money_cents"
    DECIMAL = "decimal"
    STRING = "string"
    BOOLEAN = "boolean"
    LIST = "list"


class RoleDefinition(BaseModel):
    """Declared application role or principal classification."""

    role_name: str = Field(
        ..., description="Role identifier, e.g. CUSTOMER_SUPPORT or GUEST"
    )
    description: str | None = Field(
        default=None, description="Role purpose and responsibility"
    )
    is_privileged: bool = Field(
        default=False, description="Whether role has administrative privileges"
    )
    trust_tier: TrustClassification = Field(
        default=TrustClassification.AUTHENTICATED_USER,
        description="Assigned baseline authority tier",
    )


class ToolParameterSchema(BaseModel):
    """Schema descriptor for a tool parameter."""

    param_name: str
    data_type: FieldDataType
    description: str | None = None
    required: bool = True
    minimum: float | int | None = None
    maximum: float | int | None = None
    allowed_values: list[Any] | None = None


class ToolMapping(BaseModel):
    """Mapping from high-level policy action to executable tool schema."""

    action_name: str = Field(..., description="Policy action name, e.g. issue_refund")
    tool_name: str = Field(..., description="Target tool name, e.g. issue_refund_tool")
    target_resource_type: str = Field(
        ..., description="Associated resource entity type, e.g. orders"
    )
    description: str | None = Field(default=None)
    parameters: dict[str, ToolParameterSchema] = Field(
        default_factory=dict, description="Parameter schema mappings"
    )


class ResourceDefinition(BaseModel):
    """Declared resource type and ownership attributes."""

    resource_type: str = Field(
        ..., description="Entity type, e.g. orders, user_profile, booking"
    )
    id_field: str = Field(default="id", description="Primary identifier field name")
    description: str | None = Field(default=None)
    ownership_field: str | None = Field(
        default="user_id", description="Field indicating entity owner"
    )


class FieldTypeDefinition(BaseModel):
    """Value domain and typing for policy-relevant arguments."""

    field_path: str = Field(..., description="Field path, e.g. amount, role, recipient")
    data_type: FieldDataType = Field(..., description="Data type")
    unit: str | None = Field(default=None, description="Unit e.g. cents, USD")
    min_value: int | float | None = Field(default=None)
    max_value: int | float | None = Field(default=None)
    step: int | float | None = Field(default=100)
    allowed_values: list[Any] | None = Field(default=None)


class ApprovalStateDefinition(BaseModel):
    """Declared representation of approval status in application context."""

    approver_role: str = Field(..., description="Required approver role, e.g. MANAGER")
    representation: str = Field(
        default="explicit_record",
        description="Representation mechanism: explicit_record, session_token, database_flag",
    )
    target_actions: list[str] = Field(
        default_factory=list, description="Actions requiring this approval"
    )


class SyntheticFixtureMetadata(BaseModel):
    """Synthetic test fixture references and state facts."""

    fixture_id: str = Field(..., description="Unique fixture identifier")
    fixture_version: str = Field(default="1.0.0")
    principals: dict[str, Any] = Field(
        default_factory=dict, description="Principal identities and role assignments"
    )
    resources: dict[str, Any] = Field(
        default_factory=dict,
        description="Synthetic resource states e.g. orders, bookings",
    )
    context_facts: dict[str, Any] = Field(
        default_factory=dict, description="Preconditions and environmental facts"
    )


class ProtectedDataClassification(BaseModel):
    """Protected synthetic data tokens, canaries, and permitted destinations."""

    data_type: str = Field(
        ..., description="Data category, e.g. customer_pii, secret_token"
    )
    classification_level: str = Field(default="CONFIDENTIAL")
    canary_markers: list[str] = Field(
        ...,
        min_length=1,
        description="Unique synthetic canary tokens (never real credentials)",
    )
    permitted_recipients: list[str] = Field(
        default_factory=list,
        description="Roles or recipients permitted to receive data",
    )
    prohibited_recipients: list[str] = Field(
        default_factory=list,
        description="Recipients explicitly prohibited from receiving data",
    )


class UntrustedSourceDefinition(BaseModel):
    """Declared placement location for indirect prompt injection."""

    source_id: str = Field(
        ..., description="Source identifier, e.g. ticket_body_stream"
    )
    source_type: SourceType = Field(
        ..., description="Channel category, e.g. SUPPORT_TICKET"
    )
    placement_field: str = Field(
        ..., description="Field where untrusted text appears, e.g. ticket_body, message"
    )
    trust_classification: TrustClassification = Field(
        default=TrustClassification.UNTRUSTED_CONTENT,
        description="Authority tier: strictly UNTRUSTED_CONTENT or UNTRUSTED_EXTERNAL",
    )
    description: str | None = Field(default=None)


class DomainBinding(BaseModel):
    """
    Project-scoped domain facts and adapter capabilities for test generation.
    Provides necessary context without altering accepted policy contracts.
    """

    project_id: str = Field(..., description="Scoping project identifier")
    domain_id: str = Field(
        ..., description="Domain identifier, e.g. nexacart, booking_service"
    )
    binding_version: str = Field(
        default="1.0.0", description="Immutable binding version"
    )
    description: str | None = Field(default=None)

    roles: list[RoleDefinition] = Field(default_factory=list)
    tools: list[ToolMapping] = Field(default_factory=list)
    resources: list[ResourceDefinition] = Field(default_factory=list)
    field_types: dict[str, FieldTypeDefinition] = Field(default_factory=dict)
    approval_states: list[ApprovalStateDefinition] = Field(default_factory=list)
    synthetic_fixtures: list[SyntheticFixtureMetadata] = Field(default_factory=list)
    protected_data: list[ProtectedDataClassification] = Field(default_factory=list)
    untrusted_sources: list[UntrustedSourceDefinition] = Field(default_factory=list)
    declared_capabilities: list[str] = Field(
        default_factory=list,
        description="Adapter evidence collection capabilities, e.g. ['action_attempt', 'approval_record']",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def get_role(self, role_name: str) -> RoleDefinition | None:
        return next(
            (r for r in self.roles if r.role_name.upper() == role_name.upper()), None
        )

    def get_tool_for_action(self, action_name: str) -> ToolMapping | None:
        return next((t for t in self.tools if t.action_name == action_name), None)

    def get_resource(self, resource_type: str) -> ResourceDefinition | None:
        return next(
            (r for r in self.resources if r.resource_type == resource_type), None
        )

    def get_fixture(self, fixture_id: str) -> SyntheticFixtureMetadata | None:
        return next(
            (f for f in self.synthetic_fixtures if f.fixture_id == fixture_id), None
        )

    def get_untrusted_source(
        self, source_type: SourceType
    ) -> UntrustedSourceDefinition | None:
        return next(
            (s for s in self.untrusted_sources if s.source_type == source_type), None
        )

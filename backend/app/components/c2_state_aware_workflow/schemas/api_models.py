"""Pydantic API request and response schemas for C2 workflow model endpoints."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from app.components.c2_state_aware_workflow.contracts.efsm import (
    WorkflowModelDefinition,
)
from app.components.c2_state_aware_workflow.contracts.enums import (
    LifecycleStatus,
)
from app.components.c2_state_aware_workflow.contracts.workflow_input import (
    WorkflowInput,
)


class CreateDraftWorkflowModelRequest(BaseModel):
    """Payload to create a new draft workflow reference model."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="Project identifier, e.g. 'nexacart-qa'")
    domain: str = Field(..., description="Business domain, e.g. 'e-commerce'")
    name: str = Field(..., description="Human-readable title of the workflow model")
    description: str | None = Field(
        default=None, description="Detailed explanation of workflow"
    )
    definition: WorkflowModelDefinition = Field(
        ...,
        description="Structured FSM/EFSM behavioral reference definition",
    )


class ProposeCandidateModelRequest(BaseModel):
    """Payload to propose a candidate model from normalized workflow input."""

    model_config = ConfigDict(extra="forbid")

    workflow_input: WorkflowInput = Field(
        ..., description="Normalized workflow business input"
    )
    model_id: str | None = Field(
        default=None, description="Optional custom model ID to assign"
    )
    version: str = Field(default="1.0.0", description="Initial candidate version")


class ProposeCandidateModelResponse(BaseModel):
    """Response returned from candidate model proposal."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    candidate_model: WorkflowModelDefinition | None = None
    diagnostics: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    source_rules: list[str] = Field(default_factory=list)
    builder_provenance: str


class ValidateWorkflowModelRequest(BaseModel):
    """Optional configuration for model validation execution."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="Project identifier for scoped validation")
    config: dict[str, Any] | None = Field(
        default=None, description="Validation configuration parameters"
    )


class ApproveWorkflowModelRequest(BaseModel):
    """Payload to record human domain review and approve a validated model version."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="Project identifier")
    reviewer: str = Field(
        ..., description="Identifier of the domain reviewer or supervisor"
    )
    review_basis: str = Field(
        ...,
        description="Documented basis of review, e.g. PRD section or manual inspection",
    )
    review_notes: str | None = Field(
        default=None, description="Detailed review observations and rationale"
    )
    confirm_definition_hash: str | None = Field(
        default=None,
        description="Optional safety check: expected content hash of the approved definition",
    )
    is_development_review: bool = Field(
        default=True,
        description="Explicit flag recording whether this approval is self-reported in development",
    )


class CreateNewVersionRequest(BaseModel):
    """Payload to create a new draft version of an existing workflow model."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="Project identifier")
    version: str = Field(..., description="New version identifier, e.g. '1.1.0'")
    definition: WorkflowModelDefinition = Field(
        ..., description="Updated structured EFSM definition"
    )
    domain: str | None = Field(default=None, description="Optional domain override")
    name: str | None = Field(default=None, description="Optional model name override")
    description: str | None = Field(
        default=None, description="Optional description override"
    )


class WorkflowModelSummaryResponse(BaseModel):
    """Summary representation for listing models without full definition payload."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    model_id: str
    version: str
    schema_version: str
    project_id: str
    domain: str
    name: str
    description: str | None
    content_hash: str
    lifecycle_status: LifecycleStatus
    created_at: datetime
    updated_at: datetime


class WorkflowModelDetailResponse(WorkflowModelSummaryResponse):
    """Full detail view including full structured EFSM definition and audit fields."""

    definition: WorkflowModelDefinition
    review_basis: str | None = None
    review_notes: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None

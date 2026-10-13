"""Pydantic API request and response schemas for C2 workflow model endpoints."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field
from app.components.c2_state_aware_workflow.contracts.efsm import (
    WorkflowModelDefinition,
)
from app.components.c2_state_aware_workflow.contracts.enums import LifecycleStatus


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
    review_notes: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None

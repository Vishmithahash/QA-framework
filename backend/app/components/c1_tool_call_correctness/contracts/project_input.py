"""Project input contract for C1 test preparation and configuration."""

from typing import Optional
from pydantic import BaseModel, Field

from .tool_definition import ToolDefinition


class RequirementDefinition(BaseModel):
    """Versioned software/agent requirement and associated acceptance constraints."""

    req_id: str = Field(
        ..., description="Unique requirement identifier (e.g. 'REQ-ORD-01')"
    )
    version: str = Field(default="1.0.0", description="Requirement version string")
    description: str = Field(
        ..., description="Text description of the required behavior"
    )
    acceptance_constraints: list[str] = Field(
        default_factory=list,
        description="Explicit acceptance constraints derived from project specification",
    )

    model_config = {"extra": "forbid"}


class ToolCodeMappingReference(BaseModel):
    """Reference linking a tool definition to underlying implementation source code.

    Required only for code-level defect localization and automated repair (FR-08/FR-09).
    Optional for tool-call correctness evaluation (FR-01/FR-05).
    """

    tool_id: str = Field(..., description="Registered tool identifier")
    source_file_path: str = Field(
        ..., description="Relative path to implementation source file"
    )
    symbol_name: str = Field(
        ..., description="Function, class, or method implementing the tool"
    )
    line_start: Optional[int] = Field(
        default=None, description="Starting line number in source file"
    )
    line_end: Optional[int] = Field(
        default=None, description="Ending line number in source file"
    )

    model_config = {"extra": "forbid"}


class ProjectInput(BaseModel):
    """Project-level intake bundle for C1 testing (FR-01).

    Credentials and sensitive tokens must NEVER be stored here; use secure references
    such as 'agent_connection_ref' and 'fixture_config_ref' referencing framework secrets.
    """

    project_id: str = Field(
        ..., description="Stable project identifier (e.g. 'J26-SE-341')"
    )
    domain: str = Field(..., description="Domain name (e.g. 'NexaCart / e-commerce')")
    requirements: list[RequirementDefinition] = Field(
        default_factory=list,
        description="Versioned requirements defining expected tool behaviors",
    )
    tools: list[ToolDefinition] = Field(
        default_factory=list,
        description="Registered tools available to the agent",
    )
    agent_connection_ref: str = Field(
        ...,
        description="Reference identifier to agent endpoint/credentials stored in backend secret manager",
    )
    fixture_config_ref: str = Field(
        ...,
        description="Reference identifier to environment fixture and database reset configuration",
    )
    scenario: Optional[str] = Field(
        default=None,
        description="Optional high-level user scenario guiding task generation",
    )
    source_code_ref: Optional[str] = Field(
        default=None,
        description="Optional repository/branch reference for source code access (optional for correctness, required for diagnosis)",
    )
    tool_code_mappings: list[ToolCodeMappingReference] = Field(
        default_factory=list,
        description="Optional mappings between tools and source locations",
    )

    model_config = {"extra": "forbid"}

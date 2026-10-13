"""Tool definition contract for registered tools in the application under test."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    """Specification of a tool available to the agent under test (FR-01/FR-05)."""

    tool_id: str = Field(..., description="Stable unique tool identifier")
    tool_name: str = Field(..., description="Callable tool name (e.g. 'getOrders')")
    description: str = Field(..., description="Functional description of the tool")
    version: str = Field(
        default="1.0.0", description="SemVer or version string of the tool definition"
    )
    parameters_schema: dict[str, Any] = Field(
        ...,
        description="JSON Schema (draft-07 or 2020-12) describing expected input arguments object",
    )
    output_schema: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional JSON Schema describing expected return value structure",
    )
    requirement_refs: list[str] = Field(
        default_factory=list,
        description="Requirement IDs associated with this tool's usage and constraints",
    )

    model_config = {"extra": "forbid"}

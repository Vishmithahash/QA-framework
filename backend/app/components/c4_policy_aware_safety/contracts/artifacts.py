"""Artifact intake and source tracking contracts for Component 4."""

from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any
from pydantic import BaseModel, Field


class ArtifactKind(str, Enum):
    POLICY_DOCUMENT = "POLICY_DOCUMENT"
    ROLE_DEFINITIONS = "ROLE_DEFINITIONS"
    PERMISSIONS = "PERMISSIONS"
    REQUIREMENTS = "REQUIREMENTS"
    TOOL_SPECIFICATION = "TOOL_SPECIFICATION"


class ArtifactSection(BaseModel):
    """Identified section within an artifact with character span offsets."""

    section_id: str = Field(
        ..., description="Stable section identifier, e.g. sec-1 or refund-limits"
    )
    title: str | None = Field(
        default=None, description="Optional section heading or title"
    )
    start_char: int = Field(
        ..., ge=0, description="Start character offset in normalized text"
    )
    end_char: int = Field(
        ..., ge=0, description="End character offset in normalized text"
    )
    content: str = Field(..., description="Section text excerpt")


class ArtifactVersion(BaseModel):
    """Immutable version of a registered project artifact."""

    project_id: str = Field(..., description="Scoping project identifier")
    artifact_id: str = Field(
        ..., description="Unique artifact identifier within project"
    )
    version: str = Field(..., description="Artifact version string, e.g. 1.0.0 or v1")
    kind: ArtifactKind = Field(..., description="Category of artifact")
    content_hash: str = Field(..., description="SHA-256 digest of normalized content")
    normalized_content: str = Field(
        ..., description="Canonical normalized artifact content"
    )
    sections: list[ArtifactSection] = Field(
        default_factory=list, description="Explicit section locations"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Intake timestamp in UTC",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Intake metadata (e.g. source filename, author, format)",
    )

    @classmethod
    def compute_content_hash(cls, content: str) -> str:
        """Compute SHA-256 hash over normalized string content."""
        return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()

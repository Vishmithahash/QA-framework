"""Source reference and provenance models for policy rules."""

from typing import Any
from pydantic import BaseModel, Field


class TextSpan(BaseModel):
    """Character offsets within normalized content."""

    start_char: int = Field(..., ge=0, description="0-indexed start character")
    end_char: int = Field(..., ge=0, description="0-indexed end character (exclusive)")


class SourceReference(BaseModel):
    """Provenance pointer tying a candidate/accepted rule to source artifact evidence."""

    artifact_id: str = Field(..., description="ID of supporting artifact")
    artifact_version: str = Field(..., description="Exact artifact version")
    section_id: str | None = Field(
        default=None, description="Optional section identifier"
    )
    text_span: TextSpan | None = Field(
        default=None, description="Optional character span"
    )
    supporting_excerpt: str = Field(
        ..., min_length=1, description="Exact text excerpt supporting rule"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional provenance metadata"
    )

    def matches_content(self, normalized_content: str) -> bool:
        """Check if supporting excerpt exists within normalized content."""
        clean_excerpt = self.supporting_excerpt.strip()
        if not clean_excerpt:
            return False

        if self.text_span is not None:
            if (
                self.text_span.start_char < 0
                or self.text_span.end_char > len(normalized_content)
                or self.text_span.start_char >= self.text_span.end_char
            ):
                return False
            span_content = normalized_content[
                self.text_span.start_char : self.text_span.end_char
            ].strip()
            return clean_excerpt in span_content or span_content in clean_excerpt

        return clean_excerpt in normalized_content

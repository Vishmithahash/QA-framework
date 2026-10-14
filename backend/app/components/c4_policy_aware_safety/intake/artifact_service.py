"""Artifact intake service for registering and parsing versioned artifacts."""

from datetime import datetime, timezone
import json
import re
from typing import Any
from app.components.c4_policy_aware_safety.contracts.artifacts import (
    ArtifactKind,
    ArtifactSection,
    ArtifactVersion,
)


class ArtifactIntakeService:
    """Service for validating, normalizing, and indexing project artifacts."""

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize line endings and redundant whitespace."""
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return normalized.strip()

    @staticmethod
    def extract_markdown_sections(normalized_text: str) -> list[ArtifactSection]:
        """
        Extract sections delimited by Markdown headings (e.g. ## Heading),
        computing precise character offsets.
        """
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        matches = list(heading_pattern.finditer(normalized_text))
        sections: list[ArtifactSection] = []

        if not matches:
            # Entire content is a single default section
            sections.append(
                ArtifactSection(
                    section_id="sec-default",
                    title="Document Body",
                    start_char=0,
                    end_char=len(normalized_text),
                    content=normalized_text,
                )
            )
            return sections

        # If text precedes the first heading, capture preamble
        if matches[0].start() > 0:
            preamble = normalized_text[: matches[0].start()].strip()
            if preamble:
                sections.append(
                    ArtifactSection(
                        section_id="sec-preamble",
                        title="Preamble",
                        start_char=0,
                        end_char=matches[0].start(),
                        content=preamble,
                    )
                )

        for i, match in enumerate(matches):
            title = match.group(2).strip()
            sec_id = f"sec-{re.sub(r'[^a-zA-Z0-9_-]', '-', title.lower()).strip('-')}"
            start_pos = match.start()
            end_pos = (
                matches[i + 1].start() if i + 1 < len(matches) else len(normalized_text)
            )
            content = normalized_text[start_pos:end_pos].strip()

            sections.append(
                ArtifactSection(
                    section_id=sec_id,
                    title=title,
                    start_char=start_pos,
                    end_char=end_pos,
                    content=content,
                )
            )

        return sections

    def register_text_artifact(
        self,
        project_id: str,
        artifact_id: str,
        version: str,
        kind: ArtifactKind,
        raw_text: str,
        sections: list[ArtifactSection] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactVersion:
        """Register a normalized text artifact with section offsets."""
        if not raw_text or not raw_text.strip():
            raise ValueError("Artifact content cannot be empty.")

        normalized = self.normalize_text(raw_text)
        content_hash = ArtifactVersion.compute_content_hash(normalized)

        if sections is None or len(sections) == 0:
            sections = self.extract_markdown_sections(normalized)

        return ArtifactVersion(
            project_id=project_id,
            artifact_id=artifact_id,
            version=version,
            kind=kind,
            content_hash=content_hash,
            normalized_content=normalized,
            sections=sections,
            created_at=datetime.now(timezone.utc),
            metadata=metadata or {},
        )

    def register_json_artifact(
        self,
        project_id: str,
        artifact_id: str,
        version: str,
        kind: ArtifactKind,
        json_data: dict[str, Any] | list[Any],
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactVersion:
        """Register a structured JSON policy artifact."""
        normalized_json_str = json.dumps(json_data, indent=2, sort_keys=True)
        content_hash = ArtifactVersion.compute_content_hash(normalized_json_str)

        section = ArtifactSection(
            section_id="json-root",
            title="Structured JSON Policy",
            start_char=0,
            end_char=len(normalized_json_str),
            content=normalized_json_str,
        )

        return ArtifactVersion(
            project_id=project_id,
            artifact_id=artifact_id,
            version=version,
            kind=kind,
            content_hash=content_hash,
            normalized_content=normalized_json_str,
            sections=[section],
            created_at=datetime.now(timezone.utc),
            metadata=metadata or {},
        )

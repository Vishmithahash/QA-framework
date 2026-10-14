"""API request and response schemas for C4 endpoints."""

from typing import Any
from pydantic import BaseModel, Field
from app.components.c4_policy_aware_safety.contracts.artifacts import (
    ArtifactKind,
    ArtifactSection,
)
from app.components.c4_policy_aware_safety.contracts.evidence import C4EvidencePayload
from app.components.c4_policy_aware_safety.contracts.policy import PolicyRule
from app.components.c4_policy_aware_safety.derivation.issues import (
    CandidateValidationIssue,
)


class RegisterTextArtifactRequest(BaseModel):
    artifact_id: str
    version: str
    kind: ArtifactKind
    content: str
    sections: list[ArtifactSection] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RegisterJsonArtifactRequest(BaseModel):
    artifact_id: str
    version: str
    kind: ArtifactKind
    json_data: dict[str, Any] | list[Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeriveCandidateRulesRequest(BaseModel):
    artifact_id: str
    artifact_version: str
    extraction_method: str = Field(
        default="controlled_language",
        description="Either 'controlled_language' or 'structured_json'",
    )


class DeriveCandidateRulesResponse(BaseModel):
    candidate_rules: list[PolicyRule]
    validation_issues: list[CandidateValidationIssue]


class CreateContractRequest(BaseModel):
    contract_id: str
    version: int = 1
    rules: list[PolicyRule]
    referenced_artifact_versions: dict[str, str] = Field(default_factory=dict)


class AcceptContractRequest(BaseModel):
    accepted_by: str
    justification: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluateContractRequest(BaseModel):
    evidence: C4EvidencePayload
    benign_task_completed: bool | None = None


class ErrorResponse(BaseModel):
    error: str
    details: Any | None = None

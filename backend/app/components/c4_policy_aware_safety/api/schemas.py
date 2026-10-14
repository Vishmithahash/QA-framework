"""API request and response schemas for C4 endpoints."""

from typing import Any
from pydantic import BaseModel, Field
from app.components.c4_policy_aware_safety.contracts.artifacts import (
    ArtifactKind,
    ArtifactSection,
)
from app.components.c4_policy_aware_safety.contracts.domain_binding import (
    ApprovalStateDefinition,
    FieldTypeDefinition,
    ProtectedDataClassification,
    ResourceDefinition,
    RoleDefinition,
    SyntheticFixtureMetadata,
    ToolMapping,
    UntrustedSourceDefinition,
)
from app.components.c4_policy_aware_safety.contracts.evidence import C4EvidencePayload
from app.components.c4_policy_aware_safety.contracts.integration import TestCaseType
from app.components.c4_policy_aware_safety.contracts.policy import PolicyRule
from app.components.c4_policy_aware_safety.contracts.test_cases import GeneratedTestCase
from app.components.c4_policy_aware_safety.derivation.issues import (
    CandidateValidationIssue,
)
from app.components.c4_policy_aware_safety.generation.report import (
    C4GenerationBatchReport,
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


class RegisterDomainBindingRequest(BaseModel):
    domain_id: str
    binding_version: str = "1.0.0"
    description: str | None = None
    roles: list[RoleDefinition] = Field(default_factory=list)
    tools: list[ToolMapping] = Field(default_factory=list)
    resources: list[ResourceDefinition] = Field(default_factory=list)
    field_types: dict[str, FieldTypeDefinition] = Field(default_factory=dict)
    approval_states: list[ApprovalStateDefinition] = Field(default_factory=list)
    synthetic_fixtures: list[SyntheticFixtureMetadata] = Field(default_factory=list)
    protected_data: list[ProtectedDataClassification] = Field(default_factory=list)
    untrusted_sources: list[UntrustedSourceDefinition] = Field(default_factory=list)
    declared_capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenerateTestBatchRequest(BaseModel):
    contract_id: str
    contract_version: int
    domain_id: str
    domain_binding_version: str
    categories: list[TestCaseType] | None = None
    seed: int = 42
    num_cases_per_rule: int = 1


class GenerateTestBatchResponse(BaseModel):
    batch_id: str
    report: C4GenerationBatchReport
    generated_cases: list[GeneratedTestCase]


class FreezeBatchResponse(BaseModel):
    batch_id: str
    total_frozen: int
    frozen_cases: list[GeneratedTestCase]


class ErrorResponse(BaseModel):
    error: str
    details: Any | None = None

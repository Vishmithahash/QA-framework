"""Structured, versioned policy contract models for Component 4."""

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any
from pydantic import BaseModel, Field
from app.components.c4_policy_aware_safety.contracts.findings import Severity
from app.components.c4_policy_aware_safety.contracts.predicates import (
    DeclarativePredicate,
)
from app.components.c4_policy_aware_safety.contracts.sources import SourceReference
from app.components.c4_policy_aware_safety.contracts.issues import (
    CandidateValidationIssue,
)


class PolicyFamily(str, Enum):
    """The three foundational policy families for C4."""

    AUTHORIZATION = "AUTHORIZATION"
    CONFIDENTIALITY = "CONFIDENTIALITY"
    INSTRUCTION_AUTHORITY = "INSTRUCTION_AUTHORITY"


class PolicyRequirement(str, Enum):
    """Mandate type imposed by the policy rule."""

    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE = "REQUIRE"


class EvaluationBoundary(str, Enum):
    """Declared execution boundary where this rule is evaluated."""

    ATTEMPTED_ACTION = "ATTEMPTED_ACTION"
    COMMITTED_EFFECT = "COMMITTED_EFFECT"
    OUTPUT_DISCLOSURE = "OUTPUT_DISCLOSURE"
    INSTRUCTION_AUTHORITY = "INSTRUCTION_AUTHORITY"


class RuleLifecycleStatus(str, Enum):
    """Lifecycle review status of an individual policy rule."""

    CANDIDATE = "CANDIDATE"
    VALIDATED = "VALIDATED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class ContractLifecycleStatus(str, Enum):
    """Lifecycle phase of the policy contract."""

    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    ACCEPTED = "ACCEPTED"


class PrincipalSelector(BaseModel):
    """Target principal or role selector."""

    role: str | None = Field(
        default=None, description="Target role name (e.g. CUSTOMER_SUPPORT)"
    )
    principal_id: str | None = Field(
        default=None, description="Optional specific user/principal ID"
    )
    scopes: list[str] = Field(
        default_factory=list, description="Required or matched authority scopes"
    )


class ActionSelector(BaseModel):
    """Target action or tool selector."""

    action: str = Field(
        ..., description="Action name, e.g. issue_refund or read_customer_data"
    )
    tool_name: str | None = Field(
        default=None, description="Matched tool name if specific"
    )


class ResourceSelector(BaseModel):
    """Target resource selector."""

    resource_type: str = Field(
        ..., description="Target entity type, e.g. orders, user_profile"
    )
    resource_id: str | None = Field(
        default=None, description="Optional resource instance ID"
    )


class PolicyRule(BaseModel):
    """Machine-readable, source-linked policy rule."""

    rule_id: str = Field(..., description="Stable rule identifier")
    rule_version: int = Field(default=1, ge=1, description="Immutable version integer")
    family: PolicyFamily = Field(..., description="Policy family")
    description: str | None = Field(
        default=None, description="Human-readable description of intent"
    )

    # Selectors
    principal_selector: PrincipalSelector = Field(default_factory=PrincipalSelector)
    action_selector: ActionSelector = Field(...)
    resource_selector: ResourceSelector = Field(...)

    # Applicability condition (separated from requirement: if false, rule does not apply)
    applicability: DeclarativePredicate | None = Field(
        default=None,
        description="Conditions under which this rule applies. If false, rule is NOT_EXERCISED.",
    )

    # Policy requirement and condition
    requirement: PolicyRequirement = Field(..., description="ALLOW, DENY, or REQUIRE")
    compliance_condition: DeclarativePredicate | None = Field(
        default=None,
        description="Predicate that establishes compliance (e.g. approval.approved == True)",
    )
    violation_condition: DeclarativePredicate | None = Field(
        default=None,
        description="Predicate that establishes direct violation",
    )

    # Evaluation boundary and requirements
    evaluation_boundary: EvaluationBoundary = Field(
        ...,
        description="Declared evaluation boundary (ATTEMPTED_ACTION, COMMITTED_EFFECT, etc.)",
    )
    required_evidence: list[str] = Field(
        default_factory=list,
        description="List of required evidence items (e.g. ['action_attempt', 'approval_record'])",
    )
    severity: Severity = Field(default=Severity.HIGH)

    # Provenance
    sources: list[SourceReference] = Field(
        ...,
        min_length=1,
        description="At least one supporting source reference is required",
    )

    # Status
    status: RuleLifecycleStatus = Field(default=RuleLifecycleStatus.CANDIDATE)
    acceptance_metadata: dict[str, Any] | None = Field(default=None)


class PolicyContract(BaseModel):
    """Immutable, versioned policy contract for a project."""

    contract_id: str = Field(..., description="Stable contract identifier")
    project_id: str = Field(..., description="Scoping project identifier")
    version: int = Field(
        default=1, ge=1, description="Monotonically increasing version integer"
    )
    lifecycle_status: ContractLifecycleStatus = Field(
        default=ContractLifecycleStatus.DRAFT
    )
    rules: list[PolicyRule] = Field(default_factory=list)
    referenced_artifact_versions: dict[str, str] = Field(
        default_factory=dict,
        description="Map of artifact_id -> exact artifact version",
    )
    content_hash: str = Field(default="", description="SHA-256 hash of rules content")
    validation_issues: list[CandidateValidationIssue] = Field(default_factory=list)
    acceptance_metadata: dict[str, Any] | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def compute_content_hash(self) -> str:
        """Compute SHA-256 digest over canonical JSON representation of rules."""
        rules_data = [rule.model_dump(mode="json") for rule in self.rules]
        payload = json.dumps(rules_data, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

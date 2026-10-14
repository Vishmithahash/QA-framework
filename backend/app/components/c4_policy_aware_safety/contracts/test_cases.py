"""Generated test case contracts and immutable version models for Component 4 Phase 2.

Preserves strict decoupling between agent-facing payloads and hidden evaluator-only expectations.
"""

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any
from pydantic import BaseModel, Field
from app.components.c4_policy_aware_safety.contracts.evidence import (
    SourceType,
    TrustClassification,
)
from app.components.c4_policy_aware_safety.contracts.findings import (
    PolicyVerdict,
    ReasonCode,
    ViolationStage,
)
from app.components.c4_policy_aware_safety.contracts.integration import TestCaseType
from app.components.c4_policy_aware_safety.contracts.policy import EvaluationBoundary


class TestCaseLifecycleStatus(str, Enum):
    """Lifecycle phase of generated test cases."""

    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    FROZEN = "FROZEN"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class InjectionPlacement(BaseModel):
    """Declared placement location and trust tier for prompt injection."""

    source_type: SourceType = Field(..., description="Category of input channel")
    field_name: str = Field(
        ..., description="Field holding injection, e.g. ticket_body"
    )
    source_id: str = Field(..., description="Source identifier")
    trust_classification: TrustClassification = Field(
        default=TrustClassification.UNTRUSTED_CONTENT,
        description="Assigned authority tier (strictly UNTRUSTED_CONTENT or UNTRUSTED_EXTERNAL)",
    )


class ExpectedPolicyBehavior(BaseModel):
    """Deterministic expected safe outcome derived from accepted policy rules."""

    expected_verdict: PolicyVerdict = Field(
        default=PolicyVerdict.PASS,
        description="Expected compliance outcome under policy (safe decline/defense is PASS)",
    )
    expected_violation_stage: ViolationStage | None = Field(
        default=None,
        description="Violation stage if case is expected to violate policy",
    )
    expected_reason_codes: list[ReasonCode] = Field(
        default_factory=list,
        description="Expected reason codes under compliant or non-compliant behavior",
    )
    derivation_basis: str = Field(
        ...,
        description="Human and machine-readable explanation of how expected behavior was derived from rule",
    )
    evaluation_boundary: EvaluationBoundary = Field(
        ...,
        description="Declared execution boundary where compliance is verified",
    )
    safe_alternative: str | None = Field(
        default=None,
        description="Recommended compliant action, e.g. request approval or decline refund",
    )


class EvaluatorOnlyBundle(BaseModel):
    """
    Evaluator-only ground truth, strictly isolated from agent-facing prompts and serialization.
    Contains hidden expectations, attacker objectives, and verification canaries.
    """

    expected_policy_verdict: PolicyVerdict = Field(default=PolicyVerdict.PASS)
    expected_behavior: ExpectedPolicyBehavior = Field(...)
    attacker_objective: str | None = Field(
        default=None,
        description="Attacker objective (kept strictly separate from legitimate task)",
    )
    protected_canary_markers: list[str] = Field(
        default_factory=list,
        description="Synthetic canary tokens used to evaluate confidentiality",
    )
    hidden_reference_information: dict[str, Any] = Field(
        default_factory=dict,
        description="Ground truth reference data for evaluator assertion checks",
    )
    target_rule_evaluations: dict[str, Any] = Field(
        default_factory=dict,
        description="Expected individual rule outcomes",
    )


class AgentFacingPayload(BaseModel):
    """
    Agent-facing task instructions and environmental context.
    Strictly excludes all evaluator assertions, attacker objectives, and canary ground truth.
    """

    case_id: str
    case_version: int
    project_id: str
    agent_task_prompt: str = Field(
        ..., description="Legitimate instructions presented to the agent"
    )
    setup_facts: dict[str, Any] = Field(
        default_factory=dict,
        description="Environmental fixture facts visible to the agent",
    )
    injection_surface: dict[str, Any] | None = Field(
        default=None,
        description="Contextual source channel data (e.g. support ticket or email content)",
    )


class CaseValidationIssue(BaseModel):
    """Independent static validation issue for a generated test case."""

    code: str = Field(..., description="Category code of validation issue")
    message: str = Field(..., description="Explanation of issue")
    field: str | None = Field(default=None)
    blocking: bool = Field(
        default=True, description="True prevents transition to VALIDATED or FROZEN"
    )


class GeneratedTestCase(BaseModel):
    """
    Complete, versioned policy-aware test case.
    Guarantees immutability when FROZEN, and separates agent-facing content from evaluator assertions.
    """

    case_id: str = Field(..., description="Stable test case identifier")
    version: int = Field(default=1, ge=1, description="Immutable version integer")
    project_id: str = Field(..., description="Scoping project identifier")
    domain_id: str = Field(..., description="Target domain identifier")
    batch_id: str = Field(..., description="Associated generation batch ID")
    category: TestCaseType = Field(
        ..., description="BENIGN, DIRECT_POLICY_CHALLENGE, INDIRECT_PROMPT_INJECTION"
    )
    scenario_id: str = Field(
        ..., description="Group identifier linking related variants"
    )

    # Policy & dependency references
    target_rule_ids: list[str] = Field(
        ..., min_length=1, description="Target policy rule IDs"
    )
    target_rule_versions: dict[str, int] = Field(
        default_factory=dict, description="Rule ID -> exact rule version"
    )
    contract_id: str = Field(..., description="Policy contract ID")
    contract_version: int = Field(..., description="Target policy contract version")
    artifact_dependencies: dict[str, str] = Field(
        default_factory=dict, description="Supporting artifact IDs and versions"
    )
    domain_binding_version: str = Field(
        ..., description="Domain binding version used for generation"
    )
    fixture_version: str = Field(..., description="Fixture version referenced")

    # Generation reproducibility metadata
    generator_name: str = Field(default="C4DeterministicGenerator")
    generator_version: str = Field(default="2.0.0")
    config_digest: str = Field(..., description="Hash of generator configuration")
    seed: int = Field(
        default=42, description="Random seed for deterministic generation"
    )
    deterministic_variant_id: str = Field(
        ..., description="Unique variant tag in scenario"
    )

    # Agent-facing task and environmental setup
    agent_task_prompt: str = Field(
        ..., description="Legitimate agent task instructions"
    )
    setup_preconditions: dict[str, Any] = Field(
        default_factory=dict, description="Preconditions and synthetic fixture facts"
    )

    # Attack placement (for adversarial cases)
    injection_placement: InjectionPlacement | None = Field(default=None)
    injection_payload: str | None = Field(default=None)

    # Policy expectations
    expected_policy_behavior: ExpectedPolicyBehavior = Field(...)
    required_evidence: list[str] = Field(default_factory=list)
    planned_evaluation_boundary: EvaluationBoundary = Field(...)

    # Lifecycle and validation
    lifecycle_status: TestCaseLifecycleStatus = Field(
        default=TestCaseLifecycleStatus.DRAFT
    )
    readiness_issues: list[CaseValidationIssue] = Field(default_factory=list)

    # Evaluator-only bundle (kept strictly isolated)
    evaluator_bundle: EvaluatorOnlyBundle = Field(...)

    content_hash: str = Field(
        default="", description="SHA-256 digest of canonical case content"
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def compute_content_hash(self) -> str:
        """Compute SHA-256 digest over canonical representation excluding volatile timestamps."""
        canonical_dict = {
            "case_id": self.case_id,
            "version": self.version,
            "project_id": self.project_id,
            "domain_id": self.domain_id,
            "category": self.category.value,
            "scenario_id": self.scenario_id,
            "target_rule_ids": sorted(self.target_rule_ids),
            "target_rule_versions": self.target_rule_versions,
            "contract_id": self.contract_id,
            "contract_version": self.contract_version,
            "domain_binding_version": self.domain_binding_version,
            "fixture_version": self.fixture_version,
            "seed": self.seed,
            "agent_task_prompt": self.agent_task_prompt,
            "setup_preconditions": self.setup_preconditions,
            "injection_placement": self.injection_placement.model_dump()
            if self.injection_placement
            else None,
            "injection_payload": self.injection_payload,
            "expected_policy_behavior": self.expected_policy_behavior.model_dump(),
            "required_evidence": sorted(self.required_evidence),
            "planned_evaluation_boundary": self.planned_evaluation_boundary.value,
        }
        raw_json = json.dumps(canonical_dict, sort_keys=True)
        return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

    def build_agent_facing_payload(self) -> AgentFacingPayload:
        """
        Export strictly agent-facing payload.
        Guarantees that evaluator assertions, attacker objectives, and hidden canaries are omitted.
        """
        injection_data = None
        if self.injection_placement and self.injection_payload:
            injection_data = {
                "source_type": self.injection_placement.source_type.value,
                "placement_field": self.injection_placement.field_name,
                "source_id": self.injection_placement.source_id,
                "content": self.injection_payload,
            }

        return AgentFacingPayload(
            case_id=self.case_id,
            case_version=self.version,
            project_id=self.project_id,
            agent_task_prompt=self.agent_task_prompt,
            setup_facts=self.setup_preconditions,
            injection_surface=injection_data,
        )

    def build_evaluator_bundle(self) -> EvaluatorOnlyBundle:
        """Export evaluator-only bundle containing hidden expectations."""
        return self.evaluator_bundle.model_copy(deep=True)

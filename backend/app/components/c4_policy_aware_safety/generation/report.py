"""Generation report and coverage planning models for Component 4 Phase 2."""

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field
from app.components.c4_policy_aware_safety.contracts.integration import TestCaseType


class C4GenerationBatchReport(BaseModel):
    """
    Summary report of an automated test generation batch.
    Decouples planned test coverage from observed runtime policy coverage.
    """

    batch_id: str = Field(..., description="Unique batch identifier")
    project_id: str = Field(..., description="Project identifier")
    contract_id: str = Field(..., description="Target policy contract ID")
    contract_version: int = Field(..., description="Target policy contract version")
    domain_id: str = Field(..., description="Target domain ID")
    domain_binding_version: str = Field(..., description="Domain binding version used")

    # Generator reproducibility
    generator_name: str = Field(default="C4DeterministicGenerator")
    generator_version: str = Field(default="2.0.0")
    seed: int = Field(default=42)
    config_digest: str = Field(
        ..., description="SHA-256 digest of generation configuration"
    )

    # Scope and counts
    requested_rules: list[str] = Field(default_factory=list)
    requested_case_categories: list[TestCaseType] = Field(default_factory=list)
    total_cases_generated: int = Field(default=0)
    category_counts: dict[str, int] = Field(default_factory=dict)
    status_counts: dict[str, int] = Field(default_factory=dict)
    duplicate_count: int = Field(default=0)

    # Coverage planning (planned coverage != observed execution coverage)
    planned_rule_coverage: dict[str, int] = Field(
        default_factory=dict,
        description="Number of valid test cases generated per rule. Represents planned, NOT observed coverage.",
    )
    unsupported_or_infeasible_rules: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Rules that could not be automatically exercised due to unsupported predicates or domain gaps.",
    )
    readiness_gaps: list[str] = Field(
        default_factory=list,
        description="Missing application bindings, tools, or fixtures preventing test case generation.",
    )
    dependency_references: dict[str, Any] = Field(
        default_factory=dict,
        description="References to artifact, contract, domain binding, and fixture versions.",
    )
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

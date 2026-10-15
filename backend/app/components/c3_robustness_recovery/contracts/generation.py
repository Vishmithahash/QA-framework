"""
Versioned Pydantic schemas and contracts for Component 3 (C3) Phase 4:
Automatic Candidate Generation, Deduplication, Bounded Selection, and Frozen Suites.

All models enforce strict schemas, forbidden extra attributes, and conservative bounds.
No runtime execution, network, or database dependencies.
"""

from enum import Enum
import re
from typing import Any, Literal
from pydantic import Field, field_validator, model_validator

from app.components.c3_robustness_recovery.contracts.schemas import (
    AdapterCapabilityManifest,
    AssertionMetadata,
    CandidateFaultCase,
    EffectPhase,
    FaultFamily,
    FixtureMetadata,
    ObservationMethodMetadata,
    RecoveryContract,
    StrictBaseModel,
    TaskMetadata,
    ValidationReason,
    ValidationScope,
    ValidationStatus,
)

# Reject potential connection strings, credentials, or remote endpoints
DISALLOWED_PATTERN = re.compile(
    r"^(https?://|postgres://|postgresql://|ftp://|file://|ssh://)",
    re.IGNORECASE,
)


class GenerationStatus(str, Enum):
    """Status indicating outcome of candidate fault case generation search."""

    GENERATED = "GENERATED"
    EMPTY_SEARCH = "EMPTY_SEARCH"
    FILTERED_OUT = "FILTERED_OUT"
    INCOMPATIBLE_METADATA = "INCOMPATIBLE_METADATA"
    TRUNCATED_SEARCH = "TRUNCATED_SEARCH"


class GenerationPolicy(StrictBaseModel):
    """Bounded generation and selection policy parameters."""

    max_cases: int = Field(
        default=20,
        strict=True,
        ge=1,
        le=50,
        description="Maximum number of unique valid cases to select (1 to 50).",
    )
    max_candidates_examined: int = Field(
        default=500,
        strict=True,
        ge=1,
        le=1000,
        description="Maximum candidates to derive and statically examine before stopping (1 to 1,000).",
    )
    sampling_mode: str = Field(
        default="BOUNDARY_AND_REPRESENTATIVE",
        min_length=1,
        max_length=64,
        description="Deterministic numeric parameter sampling mode.",
    )


class GenerationFilters(StrictBaseModel):
    """Explicit filters to constrain generation scope."""

    tool_ids: list[str] | None = Field(default=None, max_length=50)
    fault_families: list[FaultFamily] | None = Field(default=None, max_length=10)
    effect_phases: list[EffectPhase] | None = Field(default=None, max_length=10)


class CaseGenerationRequest(StrictBaseModel):
    """
    Typed request payload for automated fault candidate generation and suite freezing.
    Users supply declared system metadata and requirements; they do not author individual cases.
    """

    schema_version: str = Field(default="1.0.0", min_length=1, max_length=32)
    project_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_\-\.:]+$",
        description="Identifier of the project under test.",
    )
    tasks: list[TaskMetadata] = Field(..., min_length=1, max_length=20)
    adapter_manifests: list[AdapterCapabilityManifest] = Field(
        ..., min_length=1, max_length=20
    )
    fixtures: list[FixtureMetadata] = Field(..., min_length=1, max_length=20)
    recovery_contracts: list[RecoveryContract] = Field(..., min_length=1, max_length=20)
    available_assertions: list[AssertionMetadata] = Field(
        default_factory=list, max_length=100
    )
    observation_methods: list[ObservationMethodMetadata] = Field(
        default_factory=list, max_length=100
    )
    filters: GenerationFilters | None = None
    seed: int | None = Field(
        default=None,
        strict=True,
        ge=0,
        le=2147483647,
        description="Reproducibility seed for deterministic selection ordering. Booleans are rejected.",
    )
    policy: GenerationPolicy = Field(default_factory=GenerationPolicy)

    @field_validator("project_id")
    @classmethod
    def validate_no_unsafe_urls_or_code(cls, v: str) -> str:
        if DISALLOWED_PATTERN.match(v.strip()):
            raise ValueError(
                "Executable endpoints, URLs, or connection strings are forbidden."
            )
        return v

    @model_validator(mode="before")
    @classmethod
    def accept_singular_metadata_aliases(cls, data: Any) -> Any:
        """Allow convenience singular keys (task, adapter_manifest, fixture, recovery_contract)."""
        if isinstance(data, dict):
            d = dict(data)
            if "task" in d and "tasks" not in d:
                t = d.pop("task")
                d["tasks"] = [t] if isinstance(t, dict) else t
            if "adapter_manifest" in d and "adapter_manifests" not in d:
                m = d.pop("adapter_manifest")
                d["adapter_manifests"] = [m] if isinstance(m, dict) else m
            if "fixture" in d and "fixtures" not in d:
                f = d.pop("fixture")
                d["fixtures"] = [f] if isinstance(f, dict) else f
            if "recovery_contract" in d and "recovery_contracts" not in d:
                r = d.pop("recovery_contract")
                d["recovery_contracts"] = [r] if isinstance(r, dict) else r
            return d
        return data


class GenerationCounters(StrictBaseModel):
    """Deterministic counters reporting candidate enumeration, validation, and selection."""

    examined_candidates: int = Field(..., strict=True, ge=0)
    statically_valid_candidates: int = Field(..., strict=True, ge=0)
    rejected_candidates: int = Field(..., strict=True, ge=0)
    semantic_duplicates: int = Field(..., strict=True, ge=0)
    unique_valid_candidates: int = Field(..., strict=True, ge=0)
    selected_cases: int = Field(..., strict=True, ge=0)


class CoverageSummary(StrictBaseModel):
    """Explicit coverage summary for candidate generation."""

    fault_families_eligible: list[FaultFamily] = Field(default_factory=list)
    fault_families_covered: list[FaultFamily] = Field(default_factory=list)
    tools_eligible: list[str] = Field(default_factory=list)
    tools_covered: list[str] = Field(default_factory=list)
    candidate_population_denominator: int | None = Field(
        default=None,
        description="Total candidates examined or None if search was truncated prematurely.",
    )
    is_truncated: bool = False
    notes: list[str] = Field(default_factory=list)


class FrozenSuite(StrictBaseModel):
    """
    Immutable frozen snapshot artifact of generated and selected fault cases.
    Content digest enables verification of content preservation without claiming live verification.
    """

    schema_version: str = Field(default="1.0.0", min_length=1, max_length=32)
    generator_version: str = Field(default="1.0.0", min_length=1, max_length=32)
    suite_id: str = Field(..., min_length=1, max_length=128)
    content_digest: str = Field(
        ...,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
        description="SHA-256 digest over canonical JSON of frozen content.",
    )
    project_id: str = Field(..., min_length=1, max_length=128)
    seed: int | None = None
    policy: GenerationPolicy
    input_snapshots: dict[str, Any]
    cases: list[CandidateFaultCase]
    case_fingerprints: dict[str, str]
    case_families: dict[str, str]
    recovery_contracts: dict[str, RecoveryContract]
    counters: GenerationCounters
    truncated: bool = False
    static_validation_status: ValidationStatus = ValidationStatus.STATIC_VALID
    pending_checks: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    created_at_utc: str | None = Field(
        default=None,
        description="Nondeterministic creation timestamp, excluded from content_digest.",
    )


class CaseGenerationResponse(StrictBaseModel):
    """Stateless response for POST /api/v1/c3/cases/generate."""

    validation_scope: ValidationScope = ValidationScope.STATIC_ONLY
    status: GenerationStatus
    project_id: str
    selected_cases: list[CandidateFaultCase] = Field(default_factory=list)
    frozen_suite: FrozenSuite | None = None
    counters: GenerationCounters
    rejected_summaries: list[ValidationReason] = Field(default_factory=list)
    skipped_summaries: list[dict[str, Any]] = Field(default_factory=list)
    coverage_summary: CoverageSummary
    pending_checks: list[str] = Field(default_factory=list)
    runtime_verified: Literal[False] = False
    execution_ready: Literal[False] = False
    recovery_verdict: None = None

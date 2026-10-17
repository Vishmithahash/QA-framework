"""
Versioned Pydantic schemas and contracts for Component 3 (C3):
Robustness and Failure Recovery Testing.

All models are strictly defined data/API contracts for Phase 1 static validation.
No SQLAlchemy models, database access, or runtime execution dependencies.
"""

from enum import Enum
from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing_extensions import Self


# ---------------------------------------------------------------------------
# Base Model Configuration
# ---------------------------------------------------------------------------


class StrictBaseModel(BaseModel):
    """Base model enforcing forbidden extra fields, validated assignment, and strict constraints."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FaultFamily(str, Enum):
    """The five operational fault families defined for C3 testing."""

    TIMEOUT_OR_DISCONNECTION = "TIMEOUT_OR_DISCONNECTION"
    TRANSIENT_5XX_SERVER_ERROR = "TRANSIENT_5XX_SERVER_ERROR"
    HTTP_429_RATE_LIMITING = "HTTP_429_RATE_LIMITING"
    TOOL_UNAVAILABILITY = "TOOL_UNAVAILABILITY"
    MALFORMED_OR_TRUNCATED_RESPONSE = "MALFORMED_OR_TRUNCATED_RESPONSE"


class EffectPhase(str, Enum):
    """The point in the tool execution lifecycle at which fault takes effect."""

    BEFORE_EFFECT = "BEFORE_EFFECT"
    AFTER_COMMIT = "AFTER_COMMIT"
    PARTIAL_EFFECT = "PARTIAL_EFFECT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class HookType(str, Enum):
    """Declarative interception hook for fault injection."""

    PRE_TOOL_INVOCATION = "PRE_TOOL_INVOCATION"
    DURING_TRANSPORT = "DURING_TRANSPORT"
    POST_COMMIT = "POST_COMMIT"
    ON_RESPONSE_RECEIPT = "ON_RESPONSE_RECEIPT"
    GATEWAY_INTERCEPT = "GATEWAY_INTERCEPT"


# Hooks that have verified application awareness (not just generic transport delays)
APPLICATION_AWARE_HOOKS: frozenset[HookType] = frozenset({HookType.POST_COMMIT})


class TimeoutMode(str, Enum):
    """Operational mode for timeout or disconnection fault family."""

    CONNECTION_TIMEOUT = "CONNECTION_TIMEOUT"
    READ_TIMEOUT = "READ_TIMEOUT"
    TCP_RESET = "TCP_RESET"
    DNS_FAILURE = "DNS_FAILURE"


class UnavailabilityMode(str, Enum):
    """Operational mode for tool unavailability fault family."""

    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
    MAINTENANCE_MODE = "MAINTENANCE_MODE"
    ENDPOINT_NOT_FOUND_503 = "ENDPOINT_NOT_FOUND_503"
    DEPENDENCY_OUTAGE = "DEPENDENCY_OUTAGE"


class MalformedMode(str, Enum):
    """Operational mode for malformed or truncated response fault family."""

    INVALID_JSON = "INVALID_JSON"
    TRUNCATED_JSON = "TRUNCATED_JSON"
    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
    UNEXPECTED_CONTENT_TYPE = "UNEXPECTED_CONTENT_TYPE"
    EMPTY_RESPONSE = "EMPTY_RESPONSE"


class ReleaseRuleMode(str, Enum):
    """Boundary release condition governing duration of fault injection."""

    SINGLE_CALL = "SINGLE_CALL"
    COUNT_BASED = "COUNT_BASED"
    TIME_BASED = "TIME_BASED"


class TerminalOutcome(str, Enum):
    """Permitted final outcomes for agent recovery evaluation."""

    SUCCESS = "SUCCESS"
    GRACEFUL_DEGRADATION = "GRACEFUL_DEGRADATION"
    SAFE_ABORT = "SAFE_ABORT"
    FAIL = "FAIL"


class ValidationScope(str, Enum):
    """Scope of validation performed."""

    STATIC_ONLY = "STATIC_ONLY"


class ValidationStatus(str, Enum):
    """Static validation outcome status."""

    STATIC_VALID = "STATIC_VALID"
    TEST_NOT_READY = "TEST_NOT_READY"


# ---------------------------------------------------------------------------
# Typed Fault Payloads (Discriminated Union)
# ---------------------------------------------------------------------------


class TimeoutPayload(StrictBaseModel):
    """Payload parameters for TIMEOUT_OR_DISCONNECTION family."""

    family: Literal[FaultFamily.TIMEOUT_OR_DISCONNECTION] = (
        FaultFamily.TIMEOUT_OR_DISCONNECTION
    )
    mode: TimeoutMode
    delay_ms: int = Field(
        ...,
        strict=True,
        ge=1,
        le=300000,
        description="Bounded timeout delay in milliseconds (1 to 300,000 ms).",
    )


class ServerError5xxPayload(StrictBaseModel):
    """Payload parameters for TRANSIENT_5XX_SERVER_ERROR family."""

    family: Literal[FaultFamily.TRANSIENT_5XX_SERVER_ERROR] = (
        FaultFamily.TRANSIENT_5XX_SERVER_ERROR
    )
    status_code: int = Field(
        ...,
        strict=True,
        ge=500,
        le=599,
        description="HTTP status code strictly bounded to 500-599.",
    )
    error_message: str = Field(
        default="Internal Server Error",
        min_length=1,
        max_length=512,
        description="Static error message payload.",
    )


class RateLimit429Payload(StrictBaseModel):
    """Payload parameters for HTTP_429_RATE_LIMITING family."""

    family: Literal[FaultFamily.HTTP_429_RATE_LIMITING] = (
        FaultFamily.HTTP_429_RATE_LIMITING
    )
    status_code: Literal[429] = Field(
        default=429,
        description="Fixed HTTP 429 status code.",
    )
    retry_after_seconds: int | None = Field(
        default=None,
        strict=True,
        ge=0,
        le=86400,
        description="Optional non-negative Retry-After header value in seconds.",
    )
    error_message: str = Field(
        default="Too Many Requests",
        min_length=1,
        max_length=512,
        description="Static rate limit error response message.",
    )


class ToolUnavailabilityPayload(StrictBaseModel):
    """Payload parameters for TOOL_UNAVAILABILITY family."""

    family: Literal[FaultFamily.TOOL_UNAVAILABILITY] = FaultFamily.TOOL_UNAVAILABILITY
    mode: UnavailabilityMode
    error_message: str = Field(
        default="Service Unavailable",
        min_length=1,
        max_length=512,
        description="Static unavailability error message.",
    )
    expected_downtime_seconds: float | None = Field(
        default=None,
        gt=0.0,
        le=3600.0,
        description="Optional bounded expected downtime in seconds.",
    )


class MalformedResponsePayload(StrictBaseModel):
    """Payload parameters for MALFORMED_OR_TRUNCATED_RESPONSE family."""

    family: Literal[FaultFamily.MALFORMED_OR_TRUNCATED_RESPONSE] = (
        FaultFamily.MALFORMED_OR_TRUNCATED_RESPONSE
    )
    mode: MalformedMode
    raw_fragment: str | None = Field(
        default=None,
        max_length=2048,
        description="Optional illustrative corrupted payload fragment.",
    )


FaultPayload = Annotated[
    TimeoutPayload
    | ServerError5xxPayload
    | RateLimit429Payload
    | ToolUnavailabilityPayload
    | MalformedResponsePayload,
    Field(discriminator="family"),
]


# ---------------------------------------------------------------------------
# Declarative Trigger & Release Rule
# ---------------------------------------------------------------------------


class TriggerDefinition(StrictBaseModel):
    """Fixed declarative trigger identifying tool, call occurrence, and hook."""

    tool_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_\-\.:]+$",
        description="Target tool identifier.",
    )
    call_occurrence: int = Field(
        ...,
        strict=True,
        ge=1,
        le=100,
        description="Strict 1-indexed occurrence count of target tool call to inject. Booleans are rejected.",
    )
    hook: HookType = Field(
        ...,
        description="Declarative interception hook for fault injection.",
    )


class ReleaseRule(StrictBaseModel):
    """Bounded release condition governing how long the fault remains active."""

    mode: ReleaseRuleMode
    max_fault_occurrences: int | None = Field(
        default=None,
        strict=True,
        ge=1,
        le=100,
        description="Maximum fault occurrences before release (required for COUNT_BASED).",
    )
    duration_seconds: float | None = Field(
        default=None,
        gt=0.0,
        le=3600.0,
        description="Bounded duration in seconds before release (required for TIME_BASED).",
    )

    @model_validator(mode="after")
    def validate_release_rule_coherence(self) -> Self:
        if (
            self.mode == ReleaseRuleMode.COUNT_BASED
            and self.max_fault_occurrences is None
        ):
            raise ValueError(
                "max_fault_occurrences is required when mode is COUNT_BASED."
            )
        if self.mode == ReleaseRuleMode.TIME_BASED and self.duration_seconds is None:
            raise ValueError("duration_seconds is required when mode is TIME_BASED.")
        if self.mode == ReleaseRuleMode.SINGLE_CALL:
            if (
                self.max_fault_occurrences is not None
                and self.max_fault_occurrences != 1
            ):
                raise ValueError(
                    "max_fault_occurrences must be 1 for SINGLE_CALL mode."
                )
        return self


# ---------------------------------------------------------------------------
# Adapter Capability Manifest
# ---------------------------------------------------------------------------


class ToolDeclaration(StrictBaseModel):
    """Tool metadata declared by an adapter."""

    tool_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    tool_version: str = Field(..., min_length=1, max_length=32)
    is_side_effecting: bool = Field(
        ...,
        strict=True,
        description="True if tool mutates external state; False if strictly read-only.",
    )


class AdapterCapability(StrictBaseModel):
    """Explicitly supported combination of fault family, phase, hook, and constraints."""

    fault_family: FaultFamily
    effect_phase: EffectPhase
    hook: HookType
    observation_method: str = Field(..., min_length=1, max_length=128)
    tool_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="Optional tool identifier scoping this capability.",
    )
    max_call_occurrence: int | None = Field(
        default=None,
        strict=True,
        ge=1,
        le=100,
        description="Maximum supported call occurrence count for trigger interception.",
    )
    allowed_modes: list[str] | None = None
    min_delay_ms: int | None = Field(default=None, strict=True, ge=1)
    max_delay_ms: int | None = Field(default=None, strict=True, ge=1)
    allowed_status_codes: list[int] | None = None
    max_retry_after_seconds: int | None = Field(default=None, strict=True, ge=0)
    supported_release_modes: list[ReleaseRuleMode] = Field(
        default_factory=lambda: [
            ReleaseRuleMode.SINGLE_CALL,
            ReleaseRuleMode.COUNT_BASED,
        ]
    )
    is_application_aware: bool = Field(
        default=False,
        strict=True,
        description="Declares whether this capability operates via an application-aware hook.",
    )


class AdapterCapabilityManifest(StrictBaseModel):
    """Adapter capability manifest declaring supported tools and fault combinations."""

    schema_version: str = Field(default="1.0.0", min_length=1, max_length=32)
    adapter_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    adapter_version: str = Field(..., min_length=1, max_length=32)
    tools: list[ToolDeclaration] = Field(..., min_length=1)
    capabilities: list[AdapterCapability] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_no_duplicates(self) -> Self:
        tool_ids = [t.tool_id for t in self.tools]
        if len(tool_ids) != len(set(tool_ids)):
            raise ValueError("Duplicate tool declarations in adapter manifest.")

        cap_keys = [
            (c.tool_id, c.fault_family, c.effect_phase, c.hook, c.observation_method)
            for c in self.capabilities
        ]
        if len(cap_keys) != len(set(cap_keys)):
            raise ValueError("Duplicate capability combinations in adapter manifest.")
        return self


# ---------------------------------------------------------------------------
# Candidate Fault Case
# ---------------------------------------------------------------------------


class CandidateFaultCase(StrictBaseModel):
    """Candidate fault test case defining a targeted fault episode and references."""

    schema_version: str = Field(default="1.0.0", min_length=1, max_length=32)
    project_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    case_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    case_family: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    domain: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    task_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    task_version: str = Field(..., min_length=1, max_length=32)
    tool_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    tool_version: str = Field(..., min_length=1, max_length=32)
    fixture_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    fixture_version: str = Field(..., min_length=1, max_length=32)
    adapter_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    adapter_version: str = Field(..., min_length=1, max_length=32)
    recovery_contract_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    recovery_contract_version: str = Field(..., min_length=1, max_length=32)
    trigger: TriggerDefinition
    fault_family: FaultFamily
    effect_phase: EffectPhase
    payload: FaultPayload
    release_rule: ReleaseRule
    required_assertion_ids: list[str] = Field(..., min_length=1)
    seed: int | None = Field(default=None, strict=True, ge=0, le=2147483647)
    caller_timeout_seconds: float | None = Field(
        default=None,
        gt=0.0,
        le=3600.0,
        description="Caller's expected timeout boundary for tool invocations.",
    )

    @model_validator(mode="after")
    def validate_case_consistency(self) -> Self:
        if self.trigger.tool_id != self.tool_id:
            raise ValueError("Trigger tool_id must match case tool_id.")
        if self.payload.family != self.fault_family:
            raise ValueError("Payload family must match case fault_family.")
        return self


# ---------------------------------------------------------------------------
# Recovery Contract
# ---------------------------------------------------------------------------


class RecoveryContract(StrictBaseModel):
    """
    Contract defining permitted outcomes, observation budgets, and recovery constraints.

    Counting semantics:
    - Attempt 1 is the initial tool invocation.
    - Subsequent attempts (> 1) are retries.
    - max_retries represents retries following the initial call (max_retries = max_total_attempts - 1).
    - Budgets describe what will be observed from the SUT, NOT retries added by the test harness.
    """

    contract_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    version: str = Field(..., min_length=1, max_length=32)
    permitted_terminal_outcomes: list[TerminalOutcome] = Field(..., min_length=1)
    graceful_stopping_conditions: list[str] = Field(..., min_length=1)
    max_total_attempts: int = Field(
        ...,
        strict=True,
        ge=1,
        le=100,
        description="Total invocation attempts observed for the target tool (attempt 1 is initial call).",
    )
    max_retries: int = Field(
        ...,
        strict=True,
        ge=0,
        le=99,
        description="Maximum observed retries following initial call.",
    )
    timeout_budget_seconds: float = Field(
        ...,
        gt=0.0,
        le=3600.0,
        description="Total wall-clock time budget in seconds allocated for recovery and task completion.",
    )
    required_assertion_ids: list[str] = Field(..., min_length=1)
    allow_duplicate_side_effects: bool = Field(
        default=False,
        strict=True,
        description="Whether duplicate side effects are permissible under recovery.",
    )
    truthful_completion_required: bool = Field(
        default=True,
        strict=True,
        description="Whether the agent must report truthfully if task was not completed successfully.",
    )
    forbid_unsafe_retries: bool = Field(
        default=True,
        strict=True,
        description="Whether retrying a non-idempotent or post-commit side-effecting call is classified as a recovery violation.",
    )
    rule_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Rule identifiers that later findings can reference.",
    )

    @model_validator(mode="after")
    def validate_budget_coherence(self) -> Self:
        if self.max_retries >= self.max_total_attempts:
            raise ValueError(
                "max_retries must be strictly less than max_total_attempts (attempt 1 is the initial call)."
            )
        return self


# ---------------------------------------------------------------------------
# Referenced Environment Metadata
# ---------------------------------------------------------------------------


class TaskMetadata(StrictBaseModel):
    """Task metadata needed for reference verification."""

    task_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    task_version: str = Field(..., min_length=1, max_length=32)
    domain: str = Field(..., min_length=1, max_length=128)


class FixtureMetadata(StrictBaseModel):
    """Fixture metadata declaring reset and observation capabilities."""

    fixture_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    fixture_version: str = Field(..., min_length=1, max_length=32)
    supports_reset: bool = Field(
        ...,
        strict=True,
        description="Declares whether fixture supports clean state reset before each trial.",
    )
    supports_observation: bool = Field(
        ...,
        strict=True,
        description="Declares whether fixture supports post-trial state inspection.",
    )
    has_commit_observation: bool = Field(
        default=False,
        strict=True,
        description="Declares whether fixture provides observation access to verify committed side effects.",
    )
    has_partial_effect_observation: bool = Field(
        default=False,
        strict=True,
        description="Declares whether fixture supports observation of partial side effects.",
    )


class AssertionMetadata(StrictBaseModel):
    """Referenced assertion metadata."""

    assertion_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    assertion_type: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=1, max_length=256)


class ObservationMethodMetadata(StrictBaseModel):
    """Referenced observation method metadata."""

    method_id: str = Field(
        ..., min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_\-\.:]+$"
    )
    description: str = Field(..., min_length=1, max_length=256)


class EnvironmentMetadata(StrictBaseModel):
    """Referenced environment metadata needed for static checks."""

    task: TaskMetadata
    fixture: FixtureMetadata
    available_assertions: list[AssertionMetadata] = Field(..., min_length=1)
    observation_methods: list[ObservationMethodMetadata] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Request & Response Contracts
# ---------------------------------------------------------------------------


class CaseValidationRequest(StrictBaseModel):
    """Typed request payload for static candidate case validation."""

    case: CandidateFaultCase
    adapter_manifest: AdapterCapabilityManifest
    recovery_contract: RecoveryContract
    environment_metadata: EnvironmentMetadata


class ValidationReason(StrictBaseModel):
    """Safe structured reason for test non-readiness without raw user input echo."""

    code: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=512)
    field_path: str = Field(..., min_length=1, max_length=256)


class CaseValidationResponse(StrictBaseModel):
    """Deterministic static validation response contract."""

    validation_scope: ValidationScope = ValidationScope.STATIC_ONLY
    validation_status: ValidationStatus
    execution_ready: bool = False
    pending_checks: list[str] = Field(default_factory=list)
    reasons: list[ValidationReason] = Field(default_factory=list)
    recovery_verdict: None = None


# ---------------------------------------------------------------------------
# Operational Fault Catalogue Contracts
# ---------------------------------------------------------------------------


class FaultParameterConstraints(StrictBaseModel):
    """Declared parameter constraints for a catalogue fault family."""

    allowed_modes: list[str]
    timing_bounds: dict[str, Any] | None = None
    status_code_bounds: dict[str, Any] | None = None
    retry_after_bounds: dict[str, Any] | None = None
    release_rule_modes: list[ReleaseRuleMode]


class FaultFamilyDefinition(StrictBaseModel):
    """Catalogue definition for one operational fault family."""

    family: FaultFamily
    display_name: str
    description: str
    parameter_constraints: FaultParameterConstraints
    supported_effect_phases: list[EffectPhase]
    requires_application_aware_hook_for_commit: bool
    injection_status: str = "NOT_IMPLEMENTED"


class FaultCatalogResponse(StrictBaseModel):
    """OpenAPI response model for the operational fault catalogue."""

    catalog_version: str = "1.0.0"
    phase: str = "Phase 1 - Static Foundation"
    injection_implemented: bool = False
    disclaimer: str = (
        "Fault injection is NOT implemented in Phase 1. Catalogue entries define supported operational "
        "fault families and parameter constraints for static capability and case validation. Catalogue "
        "availability does not imply adapter support or runtime exposure."
    )
    families: list[FaultFamilyDefinition]

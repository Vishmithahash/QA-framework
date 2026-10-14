"""
Runtime evidence and result contracts for Component 3 (C3) Phase 3:
Robustness and Failure Recovery Testing.

Defines schemas and enums for:
- TargetMode, CallerIdentity, TimeoutBoundary, CleanupStatus
- Interception receipts with tool-occurrence tracking
- Fixture snapshots with scoped namespace and rich logical state
- Trial evidence (Clean and Fault)
- Matched pair evidence and exposure classification decoupled from clean qualification
- Evidence linkage validation rejecting contradictory evidence
- Safe argument sanitization and fingerprinting without credential leakage
- Local artifact persistence (no DB/SQLAlchemy)
"""

from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from app.components.c3_robustness_recovery.schemas import HookType


class TrialRole(str, Enum):
    """Role of the trial in the matched pair."""

    CLEAN = "CLEAN"
    FAULT = "FAULT"


class ExecutionStatus(str, Enum):
    """Overall execution outcome of a trial."""

    COMPLETED = "COMPLETED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"
    EXECUTION_ERROR = "EXECUTION_ERROR"


class ExposureStatus(str, Enum):
    """Classification of whether the injected fault episode was exposed to the caller."""

    CONFIRMED = "CONFIRMED"
    NOT_TRIGGERED = "NOT_TRIGGERED"
    EXPOSURE_UNKNOWN = "EXPOSURE_UNKNOWN"


class RecoveryActor(str, Enum):
    """Entity initiating any observed recovery behavior."""

    AGENT = "AGENT"
    SDK = "SDK"
    SCRIPTED_CALLER = "SCRIPTED_CALLER"
    ADAPTER = "ADAPTER"
    MIDDLEWARE = "MIDDLEWARE"
    UNKNOWN = "UNKNOWN"


class CallerOutcome(str, Enum):
    """Direct outcome observed by the tool caller."""

    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class TargetMode(str, Enum):
    """Mode of the target application/tool."""

    FAKE_ADAPTER = "FAKE_ADAPTER"
    LOOPBACK_TRANSPORT_TEST = "LOOPBACK_TRANSPORT_TEST"
    LIVE_AUT = "LIVE_AUT"


class CallerIdentity(str, Enum):
    """Identity of the tool caller initiating requests."""

    SCRIPTED_CALLER = "SCRIPTED_CALLER"
    ACTUAL_TESTED_AGENT = "ACTUAL_TESTED_AGENT"


class TimeoutBoundary(str, Enum):
    """Boundary at which the timeout is delivered and observed."""

    SYNTHETIC_EXCEPTION = "SYNTHETIC_EXCEPTION"
    TOOL_CALL_DEADLINE = "TOOL_CALL_DEADLINE"
    ACTUAL_TRANSPORT_TIMEOUT = "ACTUAL_TRANSPORT_TIMEOUT"


class CleanupStatus(str, Enum):
    """Status of post-trial fixture cleanup and late effect settling."""

    CLEANUP_VERIFIED = "CLEANUP_VERIFIED"
    CLEANUP_UNCERTAIN = "CLEANUP_UNCERTAIN"
    CLEANUP_FAILED = "CLEANUP_FAILED"


def sanitize_args(args: dict[str, Any]) -> dict[str, Any]:
    """
    Sanitize tool arguments by redacting sensitive parameters (passwords, tokens,
    keys, auth, credentials) while preserving safe structural summaries.
    """
    secret_terms = (
        "token",
        "secret",
        "password",
        "key",
        "auth",
        "credential",
        "bearer",
    )
    sanitized: dict[str, Any] = {}
    for k, v in sorted(args.items()):
        if any(term in k.lower() for term in secret_terms):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_args(v)
        elif isinstance(v, list):
            sanitized[k] = [
                sanitize_args(item) if isinstance(item, dict) else str(item)
                for item in v
            ]
        else:
            sanitized[k] = str(v)
    return sanitized


def fingerprint_args(args: dict[str, Any]) -> str:
    """
    Produce a safe, deterministic SHA-256 fingerprint of sanitized tool arguments.
    Redacts sensitive key patterns to prevent credential leakage into evidence artifacts.
    """
    sanitized = sanitize_args(args)
    serialized = json.dumps(sanitized, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


class CallInterceptionReceipt(BaseModel):
    """Receipt documenting the gateway decision and outcome for a single tool call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(..., min_length=1, max_length=128)
    pair_id: str | None = None
    trial_id: str | None = None
    call_occurrence: int = Field(
        ..., ge=1, description="Global call index across trial"
    )
    tool_occurrence: int = Field(
        default=1, ge=1, description="Tool-specific call occurrence index"
    )
    tool_id: str = Field(..., min_length=1, max_length=128)
    args_fingerprint: str = Field(..., min_length=1, max_length=64)
    sanitized_args: dict[str, Any] = Field(default_factory=dict)
    hook: HookType
    reached_hook: bool = True
    forwarded_to_target: bool
    fault_injected: bool
    caller_outcome: CallerOutcome
    duration_ms: float = Field(..., ge=0.0)
    timestamp_utc: str
    timeout_boundary: TimeoutBoundary = TimeoutBoundary.TOOL_CALL_DEADLINE
    is_synthetic: bool = False
    details: str | None = None


class FixtureSnapshot(BaseModel):
    """Logical snapshot of fixture state before or after a trial."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_id: str
    fixture_version: str
    namespace: str = "default"
    state_fingerprint: str
    record_count: int = Field(default=0, ge=0)
    observed_state_summary: dict[str, Any] = Field(default_factory=dict)
    timestamp_utc: str


class TrialEvidence(BaseModel):
    """Evidence collected from a single trial (clean control or fault run)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trial_id: str
    pair_id: str | None = None
    trial_role: TrialRole
    execution_status: ExecutionStatus
    clean_qualified: bool | None = (
        None  # True/False for clean trial; None for fault trial
    )
    initial_fixture: FixtureSnapshot
    final_fixture: FixtureSnapshot | None = None
    settling_fixture: FixtureSnapshot | None = None
    intercepted_calls: list[CallInterceptionReceipt] = Field(default_factory=list)
    total_calls_observed: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    recovery_actor: RecoveryActor = RecoveryActor.UNKNOWN
    cleanup_status: CleanupStatus = CleanupStatus.CLEANUP_VERIFIED
    error_message: str | None = None


class MatchedPairEvidence(BaseModel):
    """
    Versioned evidence contract for a matched clean/fault pair.

    Key guarantees:
    - Decoupled statuses: execution_status, clean_qualification, and exposure_status.
    - Clean qualification failure alone does not erase confirmed fault exposure.
    - recovery_verdict is strictly None (null) throughout Phase 3.
    - Redacted argument fingerprints and sanitized summaries.
    - Fully linked identifiers across pair, trials, and receipts.
    - Records interpretation limitations when clean baseline or cleanup is compromised.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.1.0"
    project_id: str
    case_id: str
    pair_id: str
    run_id: str
    timestamp_utc: str

    target_mode: TargetMode = TargetMode.FAKE_ADAPTER
    caller_identity: CallerIdentity = CallerIdentity.SCRIPTED_CALLER
    timeout_boundary: TimeoutBoundary = TimeoutBoundary.TOOL_CALL_DEADLINE
    timeout_boundary_subtype: str | None = None

    # Frozen configuration snapshot across both trials
    case_snapshot: dict[str, Any]
    recovery_contract_snapshot: dict[str, Any]
    adapter_version_snapshot: dict[str, str]
    environment_snapshot: dict[str, Any]

    clean_trial: TrialEvidence
    fault_trial: TrialEvidence

    clean_qualified: bool | None = None
    exposure_status: ExposureStatus
    exposure_supporting_references: list[str] = Field(default_factory=list)
    interpretation_limitations: list[str] = Field(default_factory=list)

    fixture_equivalence: bool = True
    cleanup_status: CleanupStatus = CleanupStatus.CLEANUP_VERIFIED
    fixture_reusable: bool = True

    recovery_verdict: None = None  # Strictly null in Phase 3

    is_harness_demonstration: bool = True
    target_tool: str
    notes: list[str] = Field(default_factory=list)


class EvidenceLinkageError(ValueError):
    """Raised when evidence receipts or snapshots fail internal correlation or integrity checks."""


def validate_evidence_linkage(evidence: MatchedPairEvidence) -> list[str]:
    """
    Verify that linked evidence across trials and receipts is coherent and non-contradictory.
    Returns list of issue descriptions (empty if valid).
    """
    issues: list[str] = []

    # Check clean trial linkage
    for r in evidence.clean_trial.intercepted_calls:
        if r.pair_id and r.pair_id != evidence.pair_id:
            issues.append(
                f"Clean trial receipt {r.event_id} pair_id '{r.pair_id}' does not match '{evidence.pair_id}'."
            )
        if r.trial_id and r.trial_id != evidence.clean_trial.trial_id:
            issues.append(
                f"Clean trial receipt {r.event_id} trial_id '{r.trial_id}' does not match '{evidence.clean_trial.trial_id}'."
            )
        if r.fault_injected:
            issues.append(
                f"Clean trial receipt {r.event_id} improperly indicates fault_injected=True."
            )

    # Check fault trial linkage
    for r in evidence.fault_trial.intercepted_calls:
        if r.pair_id and r.pair_id != evidence.pair_id:
            issues.append(
                f"Fault trial receipt {r.event_id} pair_id '{r.pair_id}' does not match '{evidence.pair_id}'."
            )
        if r.trial_id and r.trial_id != evidence.fault_trial.trial_id:
            issues.append(
                f"Fault trial receipt {r.event_id} trial_id '{r.trial_id}' does not match '{evidence.fault_trial.trial_id}'."
            )
        # Contradiction check: BEFORE_EFFECT fault cannot both inject fault and forward to target
        if r.fault_injected and r.forwarded_to_target:
            issues.append(
                f"Contradictory receipt {r.event_id}: BEFORE_EFFECT fault cannot both inject fault and forward to target."
            )

    return issues


def current_utc_iso() -> str:
    """Return current UTC timestamp formatted as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def save_evidence_artifact(
    evidence: MatchedPairEvidence, output_dir: Path | str
) -> Path:
    """
    Save the matched pair evidence to a local versioned JSON file.
    Does not use database persistence or background services.
    Ensures safe unique filenames to prevent accidental overwrites.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    file_path = out_path / f"matched_pair_{evidence.pair_id}.json"
    content = evidence.model_dump_json(indent=2)
    file_path.write_text(content, encoding="utf-8")
    return file_path

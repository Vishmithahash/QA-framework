"""
Runtime evidence and result contracts for Component 3 (C3) Phase 2:
Robustness and Failure Recovery Testing.

Defines schemas for:
- Interception receipts
- Fixture snapshots
- Trial evidence (Clean and Fault)
- Matched pair evidence and exposure classification
- Safe argument fingerprinting without credential leakage
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
    ADAPTER = "ADAPTER"
    MIDDLEWARE = "MIDDLEWARE"
    UNKNOWN = "UNKNOWN"


class CallerOutcome(str, Enum):
    """Direct outcome observed by the tool caller."""

    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


def fingerprint_args(args: dict[str, Any]) -> str:
    """
    Produce a safe, deterministic SHA-256 fingerprint of tool arguments.
    Redacts sensitive key patterns (passwords, tokens, credentials, auth)
    to prevent credential leakage into evidence artifacts.
    """
    secret_terms = ("token", "secret", "password", "key", "auth", "credential")
    sanitized: dict[str, Any] = {}
    for k, v in sorted(args.items()):
        if any(term in k.lower() for term in secret_terms):
            sanitized[k] = "[REDACTED]"
        else:
            sanitized[k] = str(v)

    serialized = json.dumps(sanitized, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


class CallInterceptionReceipt(BaseModel):
    """Receipt documenting the gateway decision and outcome for a single tool call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(..., min_length=1, max_length=128)
    call_occurrence: int = Field(..., ge=1)
    tool_id: str = Field(..., min_length=1, max_length=128)
    args_fingerprint: str = Field(..., min_length=1, max_length=64)
    hook: HookType
    reached_hook: bool = True
    forwarded_to_target: bool
    fault_injected: bool
    caller_outcome: CallerOutcome
    duration_ms: float = Field(..., ge=0.0)
    timestamp_utc: str
    is_synthetic: bool = False
    details: str | None = None


class FixtureSnapshot(BaseModel):
    """Logical snapshot of fixture state before or after a trial."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fixture_id: str
    fixture_version: str
    state_fingerprint: str
    record_count: int = Field(default=0, ge=0)
    observed_state_summary: dict[str, Any] = Field(default_factory=dict)
    timestamp_utc: str


class TrialEvidence(BaseModel):
    """Evidence collected from a single trial (clean control or fault run)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    trial_id: str
    trial_role: TrialRole
    execution_status: ExecutionStatus
    clean_qualified: bool | None = (
        None  # True/False for clean trial; None for fault trial
    )
    initial_fixture: FixtureSnapshot
    final_fixture: FixtureSnapshot | None = None
    intercepted_calls: list[CallInterceptionReceipt] = Field(default_factory=list)
    total_calls_observed: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    recovery_actor: RecoveryActor = RecoveryActor.UNKNOWN
    error_message: str | None = None


class MatchedPairEvidence(BaseModel):
    """
    Versioned evidence contract for a matched clean/fault pair.

    Key guarantees:
    - Decoupled statuses: execution_status, clean_qualification, and exposure_status.
    - recovery_verdict is strictly None (null) in Phase 2.
    - Redacted argument fingerprints and sanitized summaries.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0.0"
    project_id: str
    case_id: str
    pair_id: str
    run_id: str
    timestamp_utc: str

    # Frozen configuration snapshot across both trials
    case_snapshot: dict[str, Any]
    recovery_contract_snapshot: dict[str, Any]
    adapter_version_snapshot: dict[str, str]
    environment_snapshot: dict[str, Any]

    clean_trial: TrialEvidence
    fault_trial: TrialEvidence

    exposure_status: ExposureStatus
    recovery_verdict: None = None  # Intentionally null in Phase 2

    is_harness_demonstration: bool = True
    target_tool: str
    notes: list[str] = Field(default_factory=list)


def current_utc_iso() -> str:
    """Return current UTC timestamp formatted as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def save_evidence_artifact(
    evidence: MatchedPairEvidence, output_dir: Path | str
) -> Path:
    """
    Save the matched pair evidence to a local versioned JSON file.
    Does not use database persistence or background services.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    file_path = out_path / f"matched_pair_{evidence.pair_id}.json"
    content = evidence.model_dump_json(indent=2)
    file_path.write_text(content, encoding="utf-8")
    return file_path

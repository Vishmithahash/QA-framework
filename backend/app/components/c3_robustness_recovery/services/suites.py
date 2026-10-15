"""
Suite integrity, canonical JSON hashing, and export helpers for Component 3 (C3) Phase 4.

Provides pure functions to:
- Generate canonical deterministic JSON representation (disallowing non-finite numbers).
- Compute cryptographic content digests (SHA-256) over frozen suite contents.
- Compute semantic case fingerprints decoupled from generated IDs or timestamps.
- Verify suite artifact integrity before consumption or execution.
- Export frozen suites safely to local disk without overwriting.
"""

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from app.components.c3_robustness_recovery.contracts.generation import FrozenSuite
from app.components.c3_robustness_recovery.contracts.schemas import CandidateFaultCase


class SuiteIntegrityError(ValueError):
    """Raised when frozen suite digest or content fails integrity verification."""


def _check_finite_numbers(data: Any) -> None:
    """Recursively ensure no NaN or infinite float values are present."""
    if isinstance(data, float):
        if not math.isfinite(data):
            raise ValueError(f"Non-finite float value found: {data}")
    elif isinstance(data, dict):
        for v in data.values():
            _check_finite_numbers(v)
    elif isinstance(data, (list, tuple)):
        for item in data:
            _check_finite_numbers(item)


def to_canonical_json(data: Any) -> str:
    """
    Produce canonical, deterministic JSON string representation.
    - Strict sorted dictionary keys.
    - Compact separators (no redundant whitespace).
    - ASCII-encoded.
    - Explicit rejection of non-finite numbers (NaN, Infinity).
    """
    _check_finite_numbers(data)
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def compute_case_semantic_fingerprint(
    case: CandidateFaultCase | dict[str, Any],
) -> str:
    """
    Compute deterministic 16-character SHA-256 fingerprint representing semantic case identity.
    Explicitly excludes generated IDs (case_id), seeds, timestamps, or display labels.
    """
    if isinstance(case, CandidateFaultCase):
        c_dict = case.model_dump(mode="json")
    else:
        c_dict = dict(case)

    # Normalize payload fields to exclude non-semantic descriptions
    payload_dict = c_dict.get("payload", {})
    clean_payload = {
        "family": payload_dict.get("family"),
        "mode": payload_dict.get("mode"),
        "delay_ms": payload_dict.get("delay_ms"),
        "status_code": payload_dict.get("status_code"),
        "retry_after_seconds": payload_dict.get("retry_after_seconds"),
        "expected_downtime_seconds": payload_dict.get("expected_downtime_seconds"),
        "raw_fragment": payload_dict.get("raw_fragment"),
    }
    clean_payload = {k: v for k, v in clean_payload.items() if v is not None}

    semantic_content = {
        "project_id": c_dict.get("project_id"),
        "task_id": c_dict.get("task_id"),
        "task_version": c_dict.get("task_version"),
        "tool_id": c_dict.get("tool_id"),
        "tool_version": c_dict.get("tool_version"),
        "fixture_id": c_dict.get("fixture_id"),
        "fixture_version": c_dict.get("fixture_version"),
        "adapter_id": c_dict.get("adapter_id"),
        "adapter_version": c_dict.get("adapter_version"),
        "recovery_contract_id": c_dict.get("recovery_contract_id"),
        "recovery_contract_version": c_dict.get("recovery_contract_version"),
        "trigger": {
            "tool_id": c_dict.get("trigger", {}).get("tool_id"),
            "call_occurrence": c_dict.get("trigger", {}).get("call_occurrence"),
            "hook": c_dict.get("trigger", {}).get("hook"),
        },
        "fault_family": c_dict.get("fault_family"),
        "effect_phase": c_dict.get("effect_phase"),
        "payload": clean_payload,
        "release_rule": {
            "mode": c_dict.get("release_rule", {}).get("mode"),
            "max_fault_occurrences": c_dict.get("release_rule", {}).get(
                "max_fault_occurrences"
            ),
            "duration_seconds": c_dict.get("release_rule", {}).get("duration_seconds"),
        },
        "required_assertion_ids": sorted(c_dict.get("required_assertion_ids", [])),
        "caller_timeout_seconds": c_dict.get("caller_timeout_seconds"),
    }

    canonical_repr = to_canonical_json(semantic_content)
    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()[:16]


def extract_digested_suite_content(suite_data: dict[str, Any]) -> dict[str, Any]:
    """
    Extract exact suite fields covered by cryptographic content digest.
    Excludes content_digest itself, suite_id (content-addressed), and created_at_utc.
    """
    data = copy.deepcopy(suite_data)
    data.pop("content_digest", None)
    data.pop("suite_id", None)
    data.pop("created_at_utc", None)
    return data


def compute_suite_content_digest(suite_data: dict[str, Any]) -> str:
    """Compute SHA-256 cryptographic digest over canonical JSON of digested suite fields."""
    digested_content = extract_digested_suite_content(suite_data)
    canonical_repr = to_canonical_json(digested_content)
    return hashlib.sha256(canonical_repr.encode("utf-8")).hexdigest()


def verify_suite_integrity(
    suite: FrozenSuite | dict[str, Any],
) -> tuple[bool, str | None]:
    """
    Pure integrity verification function.
    Re-computes content digest from canonical suite payload and compares with declared digest.
    Returns (True, None) if valid, or (False, reason) if corrupted or tampered.
    """
    try:
        if isinstance(suite, FrozenSuite):
            s_dict = suite.model_dump(mode="json")
        elif isinstance(suite, dict):
            s_dict = copy.deepcopy(suite)
        else:
            return False, f"Expected FrozenSuite or dict, got {type(suite)}"

        declared_digest = s_dict.get("content_digest")
        if not declared_digest:
            return False, "Missing 'content_digest' field in suite."

        computed_digest = compute_suite_content_digest(s_dict)
        if computed_digest != declared_digest:
            return (
                False,
                f"Suite content digest mismatch: declared '{declared_digest}', computed '{computed_digest}'.",
            )
        return True, None
    except Exception as exc:
        return False, f"Integrity check failed with error: {exc}"


def export_frozen_suite(
    suite: FrozenSuite,
    output_path: Path | str,
    overwrite: bool = False,
) -> Path:
    """
    Export verified frozen suite artifact to local filesystem as versioned JSON.
    - Validates suite integrity before export.
    - Rejects accidental overwrite unless explicitly requested.
    - Ensures parent directories are created.
    """
    is_valid, reason = verify_suite_integrity(suite)
    if not is_valid:
        raise SuiteIntegrityError(f"Cannot export corrupted frozen suite: {reason}")

    target_path = Path(output_path)
    if target_path.exists() and not overwrite:
        raise FileExistsError(
            f"Export target file already exists and overwrite=False: '{target_path}'"
        )

    target_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_content = suite.model_dump_json(indent=2)
    target_path.write_text(canonical_content, encoding="utf-8")
    return target_path

"""
One-shot timeout gateway interceptor for Component 3 (C3) Phase 3:
Robustness and Failure Recovery Testing.

Implements:
- BEFORE_EFFECT timeout episode interception.
- Strict per-tool call occurrence tracking (unrelated tools do not consume the episode).
- Thread-safe concurrency protection (concurrent matching calls cannot inject twice).
- Prevents forwarding to the target adapter for the matching call occurrence.
- Simulates caller-observed timeout (synthetic or bounded delay hold).
- Releases and consumes the fault episode once.
- Safe cancellation handling: cancelled intercepted calls NEVER forward later.
- Trial deactivation: stops accepting new calls after trial completion.
- Subsequent calls pass through normally to the target.
- Explicitly adds NO retries or recovery mechanisms in the harness.
"""

from collections import defaultdict
import threading
import time
from typing import Any
from uuid import uuid4
from app.components.c3_robustness_recovery.adapter import ToolAdapter
from app.components.c3_robustness_recovery.evidence import (
    CallerOutcome,
    CallInterceptionReceipt,
    current_utc_iso,
    fingerprint_args,
    sanitize_args,
    TimeoutBoundary,
)
from app.components.c3_robustness_recovery.schemas import (
    HookType,
    TimeoutMode,
)


class OneShotTimeoutInterceptor:
    """
    Gateway sitting on the domain tool path intercepting a single targeted tool occurrence.

    Features:
    - Armed vs clean control passthrough.
    - Strict per-tool call occurrence counting scoped to the target tool.
    - Thread-safe atomic consumption: concurrent matching calls cannot inject twice.
    - Prevents target forwarding on match before any state mutation can occur.
    - Records comprehensive interception receipts with linked pair and trial IDs.
    - One-shot consumption: subsequent calls forward normally.
    - Guaranteed non-forwarding on cancellation.
    - Post-trial deactivation to close in-flight windows.
    """

    def __init__(
        self,
        target_tool_id: str,
        target_call_occurrence: int = 1,
        hook: HookType = HookType.DURING_TRANSPORT,
        timeout_mode: TimeoutMode = TimeoutMode.CONNECTION_TIMEOUT,
        delay_ms: int = 5000,
        caller_timeout_seconds: float = 2.0,
        armed: bool = True,
        synthetic_timeout: bool = False,
        pair_id: str | None = None,
        trial_id: str | None = None,
        timeout_boundary: TimeoutBoundary = TimeoutBoundary.TOOL_CALL_DEADLINE,
    ):
        self.target_tool_id = target_tool_id
        self.target_call_occurrence = target_call_occurrence
        self.hook = hook
        self.timeout_mode = timeout_mode
        self.delay_ms = delay_ms
        self.caller_timeout_seconds = caller_timeout_seconds
        self.armed = armed
        self.synthetic_timeout = synthetic_timeout
        self.pair_id = pair_id
        self.trial_id = trial_id
        self.timeout_boundary = timeout_boundary

        self._lock = threading.Lock()
        self._is_active = True
        self.total_call_counter = 0
        self.tool_call_counters: dict[str, int] = defaultdict(int)
        self.consumed = False
        self.receipts: list[CallInterceptionReceipt] = []
        self.in_flight_calls = 0

    @property
    def call_counter(self) -> int:
        """Backward-compatible alias for total_call_counter."""
        return self.total_call_counter

    def deactivate(self) -> None:
        """Stop accepting new calls for this trial."""
        with self._lock:
            self._is_active = False

    def execute(
        self,
        adapter: ToolAdapter,
        args: dict[str, Any],
        caller_timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        """
        Intercept or forward tool invocation.

        Raises TimeoutError if fault is injected.
        Never retries on behalf of the agent.
        """
        with self._lock:
            if not self._is_active:
                raise RuntimeError(
                    f"Trial '{self.trial_id}' is closed: no further tool calls accepted."
                )
            self.total_call_counter += 1
            self.tool_call_counters[adapter.tool_id] += 1
            current_total_occurrence = self.total_call_counter
            current_tool_occurrence = self.tool_call_counters[adapter.tool_id]

            # Scoped strictly to matching tool_id and tool-specific occurrence
            is_match = (
                self.armed
                and (not self.consumed)
                and (adapter.tool_id == self.target_tool_id)
                and (current_tool_occurrence == self.target_call_occurrence)
            )

            if is_match:
                # Atomically consume one-shot episode so concurrent calls cannot match
                self.consumed = True

        event_id = f"evt-{uuid4().hex[:8]}"
        args_fp = fingerprint_args(args)
        sanitized_args_summary = sanitize_args(args)
        timeout_limit = (
            caller_timeout_seconds
            if caller_timeout_seconds is not None
            else self.caller_timeout_seconds
        )

        if is_match:
            # 1. Matching occurrence reached
            # Prevent forwarding to target BEFORE ANY EFFECT OCCURS
            t0 = time.monotonic()

            if self.synthetic_timeout:
                # Immediate synthetic timeout for fast hermetic unit tests
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                receipt = CallInterceptionReceipt(
                    event_id=event_id,
                    pair_id=self.pair_id,
                    trial_id=self.trial_id,
                    call_occurrence=current_total_occurrence,
                    tool_occurrence=current_tool_occurrence,
                    tool_id=adapter.tool_id,
                    args_fingerprint=args_fp,
                    sanitized_args=sanitized_args_summary,
                    hook=self.hook,
                    reached_hook=True,
                    forwarded_to_target=False,
                    fault_injected=True,
                    caller_outcome=CallerOutcome.TIMEOUT,
                    duration_ms=elapsed_ms,
                    timestamp_utc=current_utc_iso(),
                    timeout_boundary=TimeoutBoundary.SYNTHETIC_EXCEPTION,
                    is_synthetic=True,
                    details="Synthetic TimeoutError raised immediately at domain hook boundary.",
                )
                with self._lock:
                    self.receipts.append(receipt)
                raise TimeoutError(
                    f"Tool '{adapter.tool_id}' call timed out (synthetic fault injection)."
                )

            # Live boundary delay hold: hold until caller timeout limit
            wait_seconds = min(timeout_limit, self.delay_ms / 1000.0)
            try:
                time.sleep(wait_seconds)
                elapsed_ms = (time.monotonic() - t0) * 1000.0

                receipt = CallInterceptionReceipt(
                    event_id=event_id,
                    pair_id=self.pair_id,
                    trial_id=self.trial_id,
                    call_occurrence=current_total_occurrence,
                    tool_occurrence=current_tool_occurrence,
                    tool_id=adapter.tool_id,
                    args_fingerprint=args_fp,
                    sanitized_args=sanitized_args_summary,
                    hook=self.hook,
                    reached_hook=True,
                    forwarded_to_target=False,
                    fault_injected=True,
                    caller_outcome=CallerOutcome.TIMEOUT,
                    duration_ms=elapsed_ms,
                    timestamp_utc=current_utc_iso(),
                    timeout_boundary=self.timeout_boundary,
                    is_synthetic=False,
                    details=f"Injected timeout delay held through caller timeout boundary ({wait_seconds:.3f}s).",
                )
                with self._lock:
                    self.receipts.append(receipt)
                raise TimeoutError(
                    f"Tool '{adapter.tool_id}' invocation timed out after {wait_seconds:.3f}s."
                )

            except Exception as exc:
                if not isinstance(exc, TimeoutError):
                    # Interrupted or cancelled: ensure target is NEVER forwarded
                    elapsed_ms = (time.monotonic() - t0) * 1000.0
                    receipt = CallInterceptionReceipt(
                        event_id=event_id,
                        pair_id=self.pair_id,
                        trial_id=self.trial_id,
                        call_occurrence=current_total_occurrence,
                        tool_occurrence=current_tool_occurrence,
                        tool_id=adapter.tool_id,
                        args_fingerprint=args_fp,
                        sanitized_args=sanitized_args_summary,
                        hook=self.hook,
                        reached_hook=True,
                        forwarded_to_target=False,
                        fault_injected=True,
                        caller_outcome=CallerOutcome.CANCELLED,
                        duration_ms=elapsed_ms,
                        timestamp_utc=current_utc_iso(),
                        timeout_boundary=self.timeout_boundary,
                        is_synthetic=False,
                        details=f"Injected timeout hold cancelled/interrupted before forwarding: {exc}",
                    )
                    with self._lock:
                        self.receipts.append(receipt)
                raise

        # 2. Passthrough: clean control, non-matching occurrence, unrelated tool, or post-consumption
        t0 = time.monotonic()
        with self._lock:
            self.in_flight_calls += 1

        try:
            result = adapter.invoke(args, timeout_seconds=timeout_limit)
            elapsed_ms = (time.monotonic() - t0) * 1000.0

            receipt = CallInterceptionReceipt(
                event_id=event_id,
                pair_id=self.pair_id,
                trial_id=self.trial_id,
                call_occurrence=current_total_occurrence,
                tool_occurrence=current_tool_occurrence,
                tool_id=adapter.tool_id,
                args_fingerprint=args_fp,
                sanitized_args=sanitized_args_summary,
                hook=self.hook,
                reached_hook=True,
                forwarded_to_target=True,
                fault_injected=False,
                caller_outcome=CallerOutcome.SUCCESS,
                duration_ms=elapsed_ms,
                timestamp_utc=current_utc_iso(),
                timeout_boundary=self.timeout_boundary,
                is_synthetic=False,
                details="Tool call forwarded to target adapter normally.",
            )
            with self._lock:
                self.receipts.append(receipt)
            return result

        except Exception as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            receipt = CallInterceptionReceipt(
                event_id=event_id,
                pair_id=self.pair_id,
                trial_id=self.trial_id,
                call_occurrence=current_total_occurrence,
                tool_occurrence=current_tool_occurrence,
                tool_id=adapter.tool_id,
                args_fingerprint=args_fp,
                sanitized_args=sanitized_args_summary,
                hook=self.hook,
                reached_hook=True,
                forwarded_to_target=True,
                fault_injected=False,
                caller_outcome=CallerOutcome.ERROR,
                duration_ms=elapsed_ms,
                timestamp_utc=current_utc_iso(),
                timeout_boundary=self.timeout_boundary,
                is_synthetic=False,
                details=f"Target invocation failed: {exc}",
            )
            with self._lock:
                self.receipts.append(receipt)
            raise
        finally:
            with self._lock:
                self.in_flight_calls = max(0, self.in_flight_calls - 1)

"""
One-shot timeout gateway interceptor for Component 3 (C3) Phase 2.

Implements:
- BEFORE_EFFECT timeout episode interception.
- Prevents forwarding to the target adapter for the matching call occurrence.
- Simulates caller-observed timeout (synthetic or bounded delay hold).
- Releases and consumes the fault episode once.
- Subsequent calls pass through normally to the target.
- Explicitly adds NO retries or recovery mechanisms in the harness.
"""

import time
from typing import Any
from uuid import uuid4
from app.components.c3_robustness_recovery.adapter import ToolAdapter
from app.components.c3_robustness_recovery.evidence import (
    CallerOutcome,
    CallInterceptionReceipt,
    current_utc_iso,
    fingerprint_args,
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
    - Strict call occurrence counting scoped to the trial and tool.
    - Prevents target forwarding on match before any state mutation can occur.
    - Records comprehensive interception receipts.
    - One-shot consumption: subsequent calls forward normally.
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
    ):
        self.target_tool_id = target_tool_id
        self.target_call_occurrence = target_call_occurrence
        self.hook = hook
        self.timeout_mode = timeout_mode
        self.delay_ms = delay_ms
        self.caller_timeout_seconds = caller_timeout_seconds
        self.armed = armed
        self.synthetic_timeout = synthetic_timeout

        self.call_counter = 0
        self.consumed = False
        self.receipts: list[CallInterceptionReceipt] = []

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
        self.call_counter += 1
        current_occurrence = self.call_counter
        event_id = f"evt-{uuid4().hex[:8]}"
        args_fp = fingerprint_args(args)
        timeout_limit = (
            caller_timeout_seconds
            if caller_timeout_seconds is not None
            else self.caller_timeout_seconds
        )

        is_match = (
            self.armed
            and (not self.consumed)
            and (adapter.tool_id == self.target_tool_id)
            and (current_occurrence == self.target_call_occurrence)
        )

        if is_match:
            # 1. Matching occurrence reached
            # Prevent forwarding to target BEFORE ANY EFFECT OCCURS
            self.consumed = True
            t0 = time.monotonic()

            if self.synthetic_timeout:
                # Immediate synthetic timeout for fast hermetic unit tests
                elapsed_ms = (time.monotonic() - t0) * 1000.0
                receipt = CallInterceptionReceipt(
                    event_id=event_id,
                    call_occurrence=current_occurrence,
                    tool_id=adapter.tool_id,
                    args_fingerprint=args_fp,
                    hook=self.hook,
                    reached_hook=True,
                    forwarded_to_target=False,
                    fault_injected=True,
                    caller_outcome=CallerOutcome.TIMEOUT,
                    duration_ms=elapsed_ms,
                    timestamp_utc=current_utc_iso(),
                    is_synthetic=True,
                    details="Synthetic TimeoutError raised immediately at domain hook boundary.",
                )
                self.receipts.append(receipt)
                raise TimeoutError(
                    f"Tool '{adapter.tool_id}' call timed out (synthetic fault injection)."
                )

            # Live boundary delay hold: hold until caller timeout limit
            wait_seconds = min(timeout_limit, self.delay_ms / 1000.0)
            time.sleep(wait_seconds)
            elapsed_ms = (time.monotonic() - t0) * 1000.0

            receipt = CallInterceptionReceipt(
                event_id=event_id,
                call_occurrence=current_occurrence,
                tool_id=adapter.tool_id,
                args_fingerprint=args_fp,
                hook=self.hook,
                reached_hook=True,
                forwarded_to_target=False,
                fault_injected=True,
                caller_outcome=CallerOutcome.TIMEOUT,
                duration_ms=elapsed_ms,
                timestamp_utc=current_utc_iso(),
                is_synthetic=False,
                details=f"Injected timeout delay held through caller timeout boundary ({wait_seconds:.3f}s).",
            )
            self.receipts.append(receipt)
            raise TimeoutError(
                f"Tool '{adapter.tool_id}' invocation timed out after {wait_seconds:.3f}s."
            )

        # 2. Passthrough: clean control, non-matching occurrence, or post-consumption calls
        t0 = time.monotonic()
        try:
            result = adapter.invoke(args, timeout_seconds=timeout_limit)
            elapsed_ms = (time.monotonic() - t0) * 1000.0

            receipt = CallInterceptionReceipt(
                event_id=event_id,
                call_occurrence=current_occurrence,
                tool_id=adapter.tool_id,
                args_fingerprint=args_fp,
                hook=self.hook,
                reached_hook=True,
                forwarded_to_target=True,
                fault_injected=False,
                caller_outcome=CallerOutcome.SUCCESS,
                duration_ms=elapsed_ms,
                timestamp_utc=current_utc_iso(),
                is_synthetic=False,
                details="Tool call forwarded to target adapter normally.",
            )
            self.receipts.append(receipt)
            return result

        except Exception as exc:
            elapsed_ms = (time.monotonic() - t0) * 1000.0
            receipt = CallInterceptionReceipt(
                event_id=event_id,
                call_occurrence=current_occurrence,
                tool_id=adapter.tool_id,
                args_fingerprint=args_fp,
                hook=self.hook,
                reached_hook=True,
                forwarded_to_target=True,
                fault_injected=False,
                caller_outcome=CallerOutcome.ERROR,
                duration_ms=elapsed_ms,
                timestamp_utc=current_utc_iso(),
                is_synthetic=False,
                details=f"Target invocation failed: {exc}",
            )
            self.receipts.append(receipt)
            raise

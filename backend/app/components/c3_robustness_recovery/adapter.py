"""
Adapter and fixture interfaces for Component 3 (C3) Phase 2.

Provides:
- Abstract ToolAdapter and FixtureManager interfaces.
- Isolated in-memory FakeNexaCartOrderToolAdapter & FakeNexaCartFixtureManager
  for hermetic tests and local runner demonstration.
- NexaCartHttpToolAdapter & NexaCartPrismaFixtureManager skeletons that mark
  live execution as explicitly BLOCKED when live prerequisites are unavailable.
"""

from abc import ABC, abstractmethod
import hashlib
import os
import time
from typing import Any
from uuid import uuid4
from app.components.c3_robustness_recovery.evidence import (
    FixtureSnapshot,
    current_utc_iso,
)


class IntegrationBlockedError(RuntimeError):
    """Raised when live target integration is blocked by missing external prerequisites."""

    def __init__(self, missing_prerequisite: str):
        super().__init__(
            f"Live NexaCart integration is BLOCKED: {missing_prerequisite}"
        )
        self.missing_prerequisite = missing_prerequisite


# ---------------------------------------------------------------------------
# Abstract Interfaces
# ---------------------------------------------------------------------------


class ToolAdapter(ABC):
    """Abstract interface representing a domain tool integration."""

    tool_id: str
    tool_version: str
    is_side_effecting: bool

    @abstractmethod
    def invoke(
        self, args: dict[str, Any], timeout_seconds: float = 5.0
    ) -> dict[str, Any]:
        """Invoke the target tool with bounded timeout."""


class FixtureManager(ABC):
    """Abstract interface representing isolated fixture preparation, reset, and observation."""

    fixture_id: str
    fixture_version: str

    @abstractmethod
    def prepare(self) -> FixtureSnapshot:
        """Prepare and verify initial fixture state."""

    @abstractmethod
    def reset(self) -> FixtureSnapshot:
        """Reset fixture to clean state."""

    @abstractmethod
    def observe(self) -> FixtureSnapshot:
        """Independently inspect current target state."""

    @abstractmethod
    def verify_clean_state(self, snapshot: FixtureSnapshot) -> bool:
        """Verify whether the snapshot represents an empty/clean initial state."""


# ---------------------------------------------------------------------------
# In-Memory Isolated Demonstration Implementation
# ---------------------------------------------------------------------------


class FakeNexaCartFixtureManager(FixtureManager):
    """
    Isolated in-memory fixture manager for the NexaCart 'create_order' tool.
    Scopes records by fixture namespace to ensure complete isolation.
    """

    def __init__(
        self,
        fixture_id: str = "fix-nexacart-orders",
        fixture_version: str = "1.0.0",
    ):
        self.fixture_id = fixture_id
        self.fixture_version = fixture_version
        self._orders: dict[str, dict[str, Any]] = {}

    def prepare(self) -> FixtureSnapshot:
        """Prepare fixture by performing a clean reset."""
        return self.reset()

    def reset(self) -> FixtureSnapshot:
        """Narrowly scoped reset wiping only this fixture's orders."""
        self._orders.clear()
        return self.observe()

    def observe(self) -> FixtureSnapshot:
        """Observe independent order state count and fingerprint."""
        order_ids = sorted(list(self._orders.keys()))
        state_repr = f"count={len(order_ids)}|ids={','.join(order_ids)}"
        state_fp = hashlib.sha256(state_repr.encode("utf-8")).hexdigest()[:16]

        return FixtureSnapshot(
            fixture_id=self.fixture_id,
            fixture_version=self.fixture_version,
            state_fingerprint=state_fp,
            record_count=len(self._orders),
            observed_state_summary={
                "order_count": len(self._orders),
                "order_ids": order_ids,
            },
            timestamp_utc=current_utc_iso(),
        )

    def verify_clean_state(self, snapshot: FixtureSnapshot) -> bool:
        """Clean state has exactly 0 orders."""
        return snapshot.record_count == 0

    def record_order(self, order_id: str, order_data: dict[str, Any]) -> None:
        """Store an order in this fixture's isolated partition."""
        self._orders[order_id] = order_data


class FakeNexaCartOrderToolAdapter(ToolAdapter):
    """
    Isolated in-memory adapter for NexaCart 'create_order' tool.
    Demonstrates side-effecting operation identity with observable state transitions.
    """

    tool_id = "create_order"
    tool_version = "1.0.0"
    is_side_effecting = True

    def __init__(self, fixture_manager: FakeNexaCartFixtureManager):
        self.fixture_manager = fixture_manager
        self.invocation_count = 0

    def invoke(
        self, args: dict[str, Any], timeout_seconds: float = 5.0
    ) -> dict[str, Any]:
        """
        Simulate creating an order in NexaCart.
        Mutates observable fixture state and returns created order summary.
        """
        self.invocation_count += 1
        order_id = f"ord-{uuid4().hex[:8]}"
        items = args.get("items", [{"sku": "SKU-DEMO-01", "quantity": 1}])
        total_amount = float(args.get("total_amount", 49.99))

        order_record = {
            "order_id": order_id,
            "items": items,
            "total_amount": total_amount,
            "status": "CREATED",
            "created_at_epoch": time.time(),
        }

        # Mutate target fixture state
        self.fixture_manager.record_order(order_id, order_record)

        return {
            "order_id": order_id,
            "status": "CREATED",
            "items_count": len(items),
            "total_amount": total_amount,
        }


# ---------------------------------------------------------------------------
# Real NexaCart Integration Skeletons (Blocked on external runtime)
# ---------------------------------------------------------------------------


class NexaCartHttpToolAdapter(ToolAdapter):
    """
    HTTP client adapter for real NexaCart NestJS application.
    Marks execution BLOCKED if NEXACART_BASE_URL is not configured.
    """

    tool_id = "create_order"
    tool_version = "1.0.0"
    is_side_effecting = True

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.environ.get("NEXACART_BASE_URL")

    def invoke(
        self, args: dict[str, Any], timeout_seconds: float = 5.0
    ) -> dict[str, Any]:
        if not self.base_url:
            raise IntegrationBlockedError(
                "NEXACART_BASE_URL environment variable is not configured."
            )
        raise IntegrationBlockedError(
            f"NexaCart host at {self.base_url} is unreachable or unverified."
        )


class NexaCartPrismaFixtureManager(FixtureManager):
    """
    Direct inspection and reset manager for NexaCart PostgreSQL/Prisma instance.
    Marks execution BLOCKED if NEXACART_DATABASE_URL is not configured.
    """

    fixture_id = "fix-nexacart-prisma"
    fixture_version = "1.0.0"

    def __init__(self, database_url: str | None = None):
        self.database_url = database_url or os.environ.get("NEXACART_DATABASE_URL")

    def prepare(self) -> FixtureSnapshot:
        if not self.database_url:
            raise IntegrationBlockedError(
                "NEXACART_DATABASE_URL environment variable is not configured."
            )
        raise IntegrationBlockedError("NexaCart database connection is not configured.")

    def reset(self) -> FixtureSnapshot:
        if not self.database_url:
            raise IntegrationBlockedError(
                "NEXACART_DATABASE_URL environment variable is not configured."
            )
        raise IntegrationBlockedError(
            "NexaCart database reset service is not configured."
        )

    def observe(self) -> FixtureSnapshot:
        if not self.database_url:
            raise IntegrationBlockedError(
                "NEXACART_DATABASE_URL environment variable is not configured."
            )
        raise IntegrationBlockedError(
            "NexaCart database observation query is not configured."
        )

    def verify_clean_state(self, snapshot: FixtureSnapshot) -> bool:
        return False

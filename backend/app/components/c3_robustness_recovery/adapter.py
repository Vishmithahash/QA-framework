"""
Adapter and fixture interfaces for Component 3 (C3) Phase 3:
Robustness and Failure Recovery Testing.

Provides:
- Abstract ToolAdapter and FixtureManager interfaces.
- Scoped, namespace-partitioned in-memory FakeNexaCartFixtureManager
  and FakeNexaCartOrderToolAdapter for hermetic tests and demonstrations.
- Independent observation of rich task-relevant state (count, IDs, total amount, fingerprints).
- Equivalence verification between trials and scoped reset.
- NexaCartHttpToolAdapter and NexaCartPrismaFixtureManager that enforce
  genuine prerequisite checks, prevent pointing at the QA Neon database,
  and mark unverified live execution as explicitly BLOCKED.
"""

from abc import ABC, abstractmethod
from collections import defaultdict
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
    def prepare(self, namespace: str = "default") -> FixtureSnapshot:
        """Prepare and verify initial fixture state."""

    @abstractmethod
    def reset(self, namespace: str = "default") -> FixtureSnapshot:
        """Reset fixture to clean state for the specified namespace."""

    @abstractmethod
    def observe(self, namespace: str = "default") -> FixtureSnapshot:
        """Independently inspect current target state for the specified namespace."""

    @abstractmethod
    def verify_clean_state(self, snapshot: FixtureSnapshot) -> bool:
        """Verify whether the snapshot represents an empty/clean initial state."""

    @abstractmethod
    def verify_equivalence(self, s1: FixtureSnapshot, s2: FixtureSnapshot) -> bool:
        """Verify logical equivalence between two initial snapshots."""

    @abstractmethod
    def cleanup(self, namespace: str = "default") -> bool:
        """Clean up resources for the specified namespace."""


# ---------------------------------------------------------------------------
# In-Memory Hardened Isolated Implementation
# ---------------------------------------------------------------------------


class FakeNexaCartFixtureManager(FixtureManager):
    """
    Hardened in-memory fixture manager for the NexaCart 'create_order' tool.
    Strictly partitions records by fixture namespace to ensure complete isolation
    between matched pair runs and trials. Never wipes unrelated records.
    """

    def __init__(
        self,
        fixture_id: str = "fix-nexacart-orders",
        fixture_version: str = "1.0.0",
    ):
        self.fixture_id = fixture_id
        self.fixture_version = fixture_version
        # Partitioned store: namespace -> {order_id: order_record}
        self._partitions: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    def prepare(self, namespace: str = "default") -> FixtureSnapshot:
        """Prepare fixture by performing a clean reset of the designated namespace."""
        return self.reset(namespace=namespace)

    def reset(self, namespace: str = "default") -> FixtureSnapshot:
        """
        Narrowly scoped reset wiping ONLY this fixture's namespace partition.
        Unrelated namespaces are strictly untouched.
        """
        self._partitions[namespace] = {}
        return self.observe(namespace=namespace)

    def observe(self, namespace: str = "default") -> FixtureSnapshot:
        """
        Observe independent order state count, IDs, total spend, and fingerprint.
        Does not rely solely on record_count=0; captures comprehensive logical state.
        """
        orders_dict = self._partitions.get(namespace, {})
        order_ids = sorted(list(orders_dict.keys()))
        total_spent = sum(
            float(o.get("total_amount", 0.0)) for o in orders_dict.values()
        )

        state_repr = (
            f"count={len(order_ids)}|ids={','.join(order_ids)}|total={total_spent:.2f}"
        )
        state_fp = hashlib.sha256(state_repr.encode("utf-8")).hexdigest()[:16]

        return FixtureSnapshot(
            fixture_id=self.fixture_id,
            fixture_version=self.fixture_version,
            namespace=namespace,
            state_fingerprint=state_fp,
            record_count=len(order_ids),
            observed_state_summary={
                "order_count": len(order_ids),
                "order_ids": order_ids,
                "total_amount_spent": round(total_spent, 2),
            },
            timestamp_utc=current_utc_iso(),
        )

    def verify_clean_state(self, snapshot: FixtureSnapshot) -> bool:
        """Clean state has exactly 0 orders and 0.0 total amount."""
        return (
            snapshot.record_count == 0
            and snapshot.observed_state_summary.get("total_amount_spent", 0.0) == 0.0
        )

    def verify_equivalence(self, s1: FixtureSnapshot, s2: FixtureSnapshot) -> bool:
        """Verify that two initial snapshots have equivalent logical states."""
        return (
            s1.record_count == s2.record_count
            and s1.observed_state_summary.get("total_amount_spent", 0.0)
            == s2.observed_state_summary.get("total_amount_spent", 0.0)
            and s1.state_fingerprint == s2.state_fingerprint
        )

    def record_order(
        self,
        order_id: str,
        order_data: dict[str, Any],
        namespace: str = "default",
    ) -> None:
        """Store an order in this fixture's isolated partition."""
        self._partitions[namespace][order_id] = order_data

    def cleanup(self, namespace: str = "default") -> bool:
        """Safely clean up namespace partition and verify it is empty."""
        self.reset(namespace=namespace)
        snap = self.observe(namespace=namespace)
        return self.verify_clean_state(snap)

    def simulate_late_effect(
        self,
        namespace: str,
        order_id: str,
        order_data: dict[str, Any] | None = None,
    ) -> None:
        """Test helper to simulate a late in-flight effect appearing after trial finish."""
        data = order_data or {
            "order_id": order_id,
            "items": [],
            "total_amount": 10.0,
            "status": "LATE_EFFECT",
        }
        self.record_order(order_id, data, namespace=namespace)


class FakeNexaCartOrderToolAdapter(ToolAdapter):
    """
    Isolated in-memory adapter for NexaCart 'create_order' tool.
    Demonstrates side-effecting operation identity with observable state transitions
    scoped to a specific trial fixture namespace.
    """

    tool_id = "create_order"
    tool_version = "1.0.0"
    is_side_effecting = True

    def __init__(
        self,
        fixture_manager: FakeNexaCartFixtureManager,
        namespace: str = "default",
    ):
        self.fixture_manager = fixture_manager
        self.namespace = namespace
        self.invocation_count = 0

    def set_namespace(self, namespace: str) -> None:
        """Update active namespace partition for the adapter."""
        self.namespace = namespace

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

        # Mutate target fixture state in the scoped namespace
        self.fixture_manager.record_order(
            order_id, order_record, namespace=self.namespace
        )

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
    Marks execution BLOCKED if NEXACART_BASE_URL is not configured
    or if verified tool endpoints are unavailable.
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
        # Even if base_url is set, real NexaCart API definitions and tools are absent in repository
        raise IntegrationBlockedError(
            f"NexaCart host at {self.base_url} is unreachable or unverified: "
            "no authoritative tool/OpenAPI contract exists in this repository."
        )


class NexaCartPrismaFixtureManager(FixtureManager):
    """
    Direct inspection and reset manager for NexaCart PostgreSQL/Prisma instance.
    Marks execution BLOCKED if NEXACART_DATABASE_URL is not configured.
    Strictly forbids pointing at the QA Neon database.
    """

    fixture_id = "fix-nexacart-prisma"
    fixture_version = "1.0.0"

    def __init__(self, database_url: str | None = None):
        self.database_url = database_url or os.environ.get("NEXACART_DATABASE_URL")
        self._verify_not_qa_database()

    def _verify_not_qa_database(self) -> None:
        """Prevent pointing fixture reset operations at the QA Neon framework database."""
        qa_db_url = os.environ.get("DATABASE_URL", "")
        if (
            self.database_url
            and qa_db_url
            and self.database_url.strip() == qa_db_url.strip()
        ):
            raise IntegrationBlockedError(
                "NEXACART_DATABASE_URL cannot point to the QA Neon framework database."
            )

    def prepare(self, namespace: str = "default") -> FixtureSnapshot:
        self._verify_not_qa_database()
        if not self.database_url:
            raise IntegrationBlockedError(
                "NEXACART_DATABASE_URL environment variable is not configured."
            )
        raise IntegrationBlockedError(
            "NexaCart database connection is not configured or unverified."
        )

    def reset(self, namespace: str = "default") -> FixtureSnapshot:
        self._verify_not_qa_database()
        if not self.database_url:
            raise IntegrationBlockedError(
                "NEXACART_DATABASE_URL environment variable is not configured."
            )
        raise IntegrationBlockedError(
            "NexaCart database reset service is not configured or unverified."
        )

    def observe(self, namespace: str = "default") -> FixtureSnapshot:
        self._verify_not_qa_database()
        if not self.database_url:
            raise IntegrationBlockedError(
                "NEXACART_DATABASE_URL environment variable is not configured."
            )
        raise IntegrationBlockedError(
            "NexaCart database observation query is not configured or unverified."
        )

    def verify_clean_state(self, snapshot: FixtureSnapshot) -> bool:
        return False

    def verify_equivalence(self, s1: FixtureSnapshot, s2: FixtureSnapshot) -> bool:
        return False

    def cleanup(self, namespace: str = "default") -> bool:
        return False

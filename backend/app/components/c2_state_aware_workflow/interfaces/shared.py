"""Shared integration interfaces for Component 2: State-Aware Multi-Step Workflow Testing.

Defines narrow, typed Python protocols establishing the boundaries between Component 2
and external shared framework services:
1. Workflow input normalization (Shared Project Intake)
2. Fixture reset (Shared Fixture Manager / Test Orchestrator)
3. Agent execution (Shared Agent Runner)
4. State observation (Runtime Evidence Collector / AUT database adapter)
5. Evidence ingestion (Shared Evidence Store)
6. Unified-report export (Shared QA Reporting Service)

BOUNDARY NOTE:
Per Phase 1 boundary rules, these interfaces are declared as typed protocols with
documented integration dependencies. Component 2 does NOT build a replacement shared
platform or invent live socket/service connections in this phase.
"""

from typing import Any, Protocol, runtime_checkable
from app.components.c2_state_aware_workflow.contracts.evaluation_result import (
    WorkflowEvaluationResult,
)
from app.components.c2_state_aware_workflow.contracts.runtime_evidence import (
    ObservedValue,
    RuntimeEvidenceEvent,
    WorkflowExecutionEvidence,
)
from app.components.c2_state_aware_workflow.contracts.workflow_input import (
    SyntheticFixtureReference,
    WorkflowInput,
)


@runtime_checkable
class WorkflowInputNormalizationInterface(Protocol):
    """Boundary interface to the Shared Project Intake service.

    Integration Dependency:
    Provided by the shared intake layer. Normalizes raw requirements documents,
    OpenAPI specifications, and database schemas into typed C2 WorkflowInput contracts.
    """

    def normalize_workflow_input(self, raw_input: dict[str, Any]) -> WorkflowInput:
        """Parses and normalizes heterogeneous project inputs into a typed WorkflowInput."""
        ...


@runtime_checkable
class FixtureResetInterface(Protocol):
    """Boundary interface to the Shared Fixture Manager.

    Integration Dependency:
    Provided by the shared test execution runner. Resets the isolated Application
    Under Test (AUT) environment to a known initial state before every test run.
    """

    def reset_fixture(self, fixture: SyntheticFixtureReference) -> bool:
        """Executes a clean reset of synthetic database tables and mock external states.

        Returns True if the fixture was successfully verified and reset.
        """
        ...


@runtime_checkable
class AgentExecutionInterface(Protocol):
    """Boundary interface to the Shared Agent Runner.

    Integration Dependency:
    Provided by the shared runner infrastructure. Dispatches the natural-language task
    prompt to the LLM agent under test in an isolated execution sandbox.
    Keeps private reference oracle paths strictly hidden from the agent.
    """

    def execute_workflow_task(
        self,
        task: str,
        fixture_id: str,
        seed: int | str,
        timeout_seconds: float = 60.0,
    ) -> str:
        """Launches the agent under test with the given prompt and returns the allocated run_id."""
        ...


@runtime_checkable
class StateObservationInterface(Protocol):
    """Boundary interface to the Runtime State Observer / AUT State Adapter.

    Integration Dependency:
    Queries the application-under-test database (e.g. NexaCart PostgreSQL)
    before and after each tool call to observe entity mutations and verify
    invariants, distinguishing explicit null values from unobserved/missing evidence.
    """

    def capture_entity_observation(
        self,
        project_id: str,
        entity_name: str,
        entity_id: Any,
        fields: list[str],
    ) -> dict[str, ObservedValue]:
        """Captures before/after entity state snapshots as typed ObservedValue mappings."""
        ...

    def compute_state_diff(
        self,
        before_state: dict[str, ObservedValue],
        after_state: dict[str, ObservedValue],
    ) -> dict[str, Any]:
        """Calculates structured delta between before and after observations."""
        ...


@runtime_checkable
class EvidenceIngestionInterface(Protocol):
    """Boundary interface to the Shared Evidence Store.

    Integration Dependency:
    Provided by the shared evidence subsystem. Streams or fetches ordered runtime
    events, tool invocation telemetry, and state diffs for a given execution run.
    """

    def ingest_runtime_event(self, event: RuntimeEvidenceEvent) -> None:
        """Appends an ordered runtime event into the evidence store."""
        ...

    def get_execution_evidence(self, run_id: str) -> WorkflowExecutionEvidence:
        """Retrieves the complete ordered evidence trace for a completed run."""
        ...


@runtime_checkable
class UnifiedReportExportInterface(Protocol):
    """Boundary interface to the Shared Report Aggregator.

    Integration Dependency:
    Provided by the shared report generator. Combines C2 workflow conformance findings,
    first-divergence localisation, and coverage metrics with findings from C1, C3, and C4.
    """

    def export_evaluation_result(
        self, result: WorkflowEvaluationResult
    ) -> dict[str, Any]:
        """Exports C2 verdict and evidence records to the unified framework report."""
        ...

"""Generated test contract for Component 2.

Captures test case metadata, natural-language prompt/task, synthetic fixture
references, private reference-path oracle information, mutation provenance,
and readiness tracking.
"""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from app.components.c2_state_aware_workflow.contracts.enums import (
    EvaluationVerdict,
    MutationType,
    TestCategory,
    TestReadinessStatus,
)
from app.components.c2_state_aware_workflow.contracts.predicates import StateEffectSpec
from app.components.c2_state_aware_workflow.contracts.workflow_input import (
    SyntheticFixtureReference,
)


class ReferencePathInfo(BaseModel):
    """Private oracle reference path retained by the QA framework.

    Must remain hidden from the tested LLM agent during execution.
    """

    model_config = ConfigDict(extra="forbid")

    state_sequence: list[str] = Field(
        ...,
        description="Expected sequence of states from initial state to goal",
    )
    transition_sequence: list[str] = Field(
        ...,
        description="Expected sequence of transition IDs",
    )
    is_hidden_from_agent: bool = Field(
        default=True,
        description="Ensures the expected sequence is never leaked in the agent task prompt",
    )


class MutationProvenance(BaseModel):
    """Detailed record of injected fault mutations for negative/mutated tests."""

    model_config = ConfigDict(extra="forbid")

    mutation_type: MutationType = Field(
        ...,
        description="Type of injected anomaly from C2 mutation catalogue",
    )
    original_target_transition: str | None = Field(
        default=None,
        description="Target transition ID modified, skipped, or reordered",
    )
    injected_fault_description: str = Field(
        ...,
        description="Human-readable description of how the workflow was mutated",
    )
    label: str = Field(..., description="Short tag or ground-truth defect label")


class TestReadiness(BaseModel):
    """Readiness status of the generated test case."""

    model_config = ConfigDict(extra="forbid")

    status: TestReadinessStatus = Field(
        default=TestReadinessStatus.READY,
        description="READY or TEST_NOT_READY (for infeasible or ambiguous paths)",
    )
    reason: str | None = Field(
        default=None,
        description="Explanation if the test is marked TEST_NOT_READY",
    )


TestReadiness.__test__ = False


class ExpectedOutcome(BaseModel):
    """Target expected outcome for test scoring."""

    model_config = ConfigDict(extra="forbid")

    expected_verdict: EvaluationVerdict = Field(
        ...,
        description="Target verdict: PASS or EXPECTED REJECTION PASS",
    )
    expected_final_state: str = Field(
        ..., description="Expected final state ID in the EFSM"
    )
    expected_state_effects: list[StateEffectSpec] = Field(
        default_factory=list,
        description="Expected persistent database/system state mutations",
    )
    expected_rejection_reason: str | None = Field(
        default=None,
        description="Explanation if expected outcome is a valid rejection",
    )


class GeneratedWorkflowTest(BaseModel):
    """Generated test case specification created from an approved EFSM."""

    model_config = ConfigDict(extra="forbid")

    test_id: str = Field(
        ..., description="Unique test case identifier, e.g. 'C2-REFUND-017'"
    )
    test_version: str = Field(
        default="1.0.0", description="Version of this generated test case"
    )
    model_id: str = Field(..., description="Reference EFSM model ID")
    model_version: str = Field(..., description="Reference EFSM model version")
    category: TestCategory = Field(
        ...,
        description="Test category: NORMAL, ALTERNATIVE, NEGATIVE, or MUTATED",
    )
    task: str = Field(
        ..., description="Natural-language task prompt provided to the agent"
    )
    fixture_reference: SyntheticFixtureReference = Field(
        ...,
        description="Resettable synthetic fixture required for execution",
    )
    seed: int | str = Field(..., description="PRNG seed for repeatable execution")
    expected_outcome: ExpectedOutcome = Field(
        ..., description="Expected final oracle outcome"
    )
    reference_path: ReferencePathInfo = Field(
        ...,
        description="Private reference path hidden from the agent under test",
    )
    mutation_provenance: MutationProvenance | None = Field(
        default=None,
        description="Mutation details if this test belongs to the MUTATED category",
    )
    readiness: TestReadiness = Field(
        default_factory=TestReadiness,
        description="Readiness assessment (READY or TEST NOT READY)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional test metadata"
    )

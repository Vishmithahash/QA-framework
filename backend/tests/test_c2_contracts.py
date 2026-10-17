"""Tests for Component 2 data contracts, declarative predicates, and validations."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError
from app.components.c2_state_aware_workflow.contracts.efsm import (
    EFSMState,
    EFSMTransition,
    EFSMVariable,
    WorkflowModelDefinition,
)
from app.components.c2_state_aware_workflow.contracts.enums import (
    EffectType,
    EvaluationVerdict,
    EvidencePresence,
    LogicalOperator,
    MutationType,
    PredicateOperator,
    ReasonCode,
    TestCategory,
    TestReadinessStatus,
)
from app.components.c2_state_aware_workflow.contracts.evaluation_result import (
    FirstDivergenceInfo,
    WorkflowCoverageInfo,
    WorkflowEvaluationResult,
    WorkflowViolation,
)
from app.components.c2_state_aware_workflow.contracts.generated_test import (
    ExpectedOutcome,
    GeneratedWorkflowTest,
    MutationProvenance,
    ReferencePathInfo,
    TestReadiness,
)
from app.components.c2_state_aware_workflow.contracts.predicates import (
    StateEffectSpec,
    StructuredPredicate,
    VariableUpdate,
)
from app.components.c2_state_aware_workflow.contracts.runtime_evidence import (
    EvidenceCompletenessInfo,
    ObservedValue,
    RuntimeEvidenceEvent,
    WorkflowExecutionEvidence,
)
from app.components.c2_state_aware_workflow.contracts.workflow_input import (
    ObservableStateMapping,
    SyntheticFixtureReference,
    ToolSpecification,
    WorkflowInput,
    WorkflowRule,
)


class TestVerdictEnums:
    """Verifies that the exact six required verdicts are defined and enforced."""

    def test_exact_six_verdicts(self):
        expected_verdicts = {
            "PASS",
            "EXPECTED REJECTION PASS",
            "FAIL",
            "INCONCLUSIVE",
            "MODEL NOT READY",
            "TEST NOT READY",
        }
        actual_verdicts = {v.value for v in EvaluationVerdict}
        assert actual_verdicts == expected_verdicts
        assert len(EvaluationVerdict) == 6

    def test_invalid_verdict_rejected(self):
        with pytest.raises(ValueError):
            EvaluationVerdict("INVENTED_VERDICT")


class TestStructuredPredicates:
    """Tests declarative predicate evaluation without eval/exec."""

    def test_leaf_operators(self):
        ctx = {
            "order_id": 503,
            "status": "PAID",
            "amount": 89.0,
            "items": ["item1", "item2"],
            "notes": None,
        }

        assert StructuredPredicate(
            field="order_id", operator=PredicateOperator.EQ, value=503
        ).evaluate(ctx)
        assert not StructuredPredicate(
            field="order_id", operator=PredicateOperator.EQ, value=501
        ).evaluate(ctx)

        assert StructuredPredicate(
            field="status", operator=PredicateOperator.NEQ, value="UNPAID"
        ).evaluate(ctx)
        assert StructuredPredicate(
            field="amount", operator=PredicateOperator.GT, value=50.0
        ).evaluate(ctx)
        assert StructuredPredicate(
            field="amount", operator=PredicateOperator.GTE, value=89.0
        ).evaluate(ctx)
        assert StructuredPredicate(
            field="amount", operator=PredicateOperator.LT, value=100.0
        ).evaluate(ctx)
        assert StructuredPredicate(
            field="amount", operator=PredicateOperator.LTE, value=89.0
        ).evaluate(ctx)
        assert StructuredPredicate(
            field="status", operator=PredicateOperator.IN, value=["PAID", "REFUNDED"]
        ).evaluate(ctx)
        assert StructuredPredicate(
            field="status", operator=PredicateOperator.NOT_IN, value=["CANCELLED"]
        ).evaluate(ctx)
        assert StructuredPredicate(
            field="items", operator=PredicateOperator.CONTAINS, value="item1"
        ).evaluate(ctx)
        assert StructuredPredicate(
            field="notes", operator=PredicateOperator.IS_NULL
        ).evaluate(ctx)
        assert StructuredPredicate(
            field="status", operator=PredicateOperator.IS_NOT_NULL
        ).evaluate(ctx)

    def test_composite_and_or_not(self):
        ctx = {"customer_id": 42, "order_status": "PAID"}

        p_and = StructuredPredicate(
            logical_op=LogicalOperator.AND,
            children=[
                StructuredPredicate(
                    field="customer_id", operator=PredicateOperator.EQ, value=42
                ),
                StructuredPredicate(
                    field="order_status", operator=PredicateOperator.EQ, value="PAID"
                ),
            ],
        )
        assert p_and.evaluate(ctx)

        p_or = StructuredPredicate(
            logical_op=LogicalOperator.OR,
            children=[
                StructuredPredicate(
                    field="customer_id", operator=PredicateOperator.EQ, value=99
                ),
                StructuredPredicate(
                    field="order_status", operator=PredicateOperator.EQ, value="PAID"
                ),
            ],
        )
        assert p_or.evaluate(ctx)

        p_not = StructuredPredicate(
            logical_op=LogicalOperator.NOT,
            children=[
                StructuredPredicate(
                    field="order_status", operator=PredicateOperator.EQ, value="UNPAID"
                ),
            ],
        )
        assert p_not.evaluate(ctx)

    def test_variable_reference_resolution(self):
        ctx = {"refund_target_id": 503, "selected_order_id": 503}
        p_ref = StructuredPredicate(
            field="refund_target_id",
            operator=PredicateOperator.MATCHES_ENTITY,
            value="selected_order_id",
            value_is_var_ref=True,
        )
        assert p_ref.evaluate(ctx)

    def test_malformed_predicates_rejected(self):
        # Empty predicate
        with pytest.raises(ValidationError):
            StructuredPredicate()

        # Both leaf and composite
        with pytest.raises(ValidationError):
            StructuredPredicate(
                field="status",
                operator=PredicateOperator.EQ,
                value="PAID",
                logical_op=LogicalOperator.AND,
                children=[],
            )

        # NOT with multiple children
        with pytest.raises(ValidationError):
            StructuredPredicate(
                logical_op=LogicalOperator.NOT,
                children=[
                    StructuredPredicate(
                        field="a", operator=PredicateOperator.EQ, value=1
                    ),
                    StructuredPredicate(
                        field="b", operator=PredicateOperator.EQ, value=2
                    ),
                ],
            )


class TestEvidencePresenceAndCompleteness:
    """Tests distinguishing explicit null from missing evidence."""

    def test_observed_value_presence_types(self):
        present = ObservedValue.of(503)
        assert present.is_present
        assert present.value == 503
        assert present.presence == EvidencePresence.PRESENT

        explicit_null = ObservedValue.explicit_null()
        assert explicit_null.is_explicit_null
        assert explicit_null.value is None
        assert explicit_null.presence == EvidencePresence.EXPLICIT_NULL

        missing = ObservedValue.missing()
        assert missing.is_missing
        assert missing.value is None
        assert missing.presence == EvidencePresence.MISSING

        # Verify they are distinguishable and not equal
        assert explicit_null != missing
        assert explicit_null != present
        assert missing != present

    def test_invalid_observed_value_combinations(self):
        # PRESENT cannot have None
        with pytest.raises(ValidationError):
            ObservedValue(value=None, presence=EvidencePresence.PRESENT)

        # EXPLICIT_NULL cannot have a value
        with pytest.raises(ValidationError):
            ObservedValue(value=503, presence=EvidencePresence.EXPLICIT_NULL)

        # MISSING cannot have a value
        with pytest.raises(ValidationError):
            ObservedValue(value="data", presence=EvidencePresence.MISSING)


class TestEFSMDefinitionValidation:
    """Tests EFSM behavioral reference model structural validations."""

    def test_valid_minimal_efsm(self):
        model = WorkflowModelDefinition(
            model_id="minimal-model",
            version="1.0.0",
            project_id="test-proj",
            domain="e-commerce",
            name="Minimal Model",
            states=[
                EFSMState(state_id="START", name="Start", is_initial=True),
                EFSMState(state_id="DONE", name="Done", is_accepting=True),
            ],
            initial_state="START",
            accepting_states=["DONE"],
            variables=[
                EFSMVariable(name="cnt", var_type="int", initial_value=0),
            ],
            transitions=[
                EFSMTransition(
                    transition_id="T_FINISH",
                    source_state="START",
                    target_state="DONE",
                    trigger_event="EV_DONE",
                    variable_updates=[
                        VariableUpdate(
                            variable_name="cnt", operation="increment", value=1
                        )
                    ],
                    expected_state_effects=[
                        StateEffectSpec(
                            entity_type="order",
                            entity_id_var="cnt",
                            field="status",
                            effect_type=EffectType.UPDATED,
                            expected_value="DONE",
                        )
                    ],
                )
            ],
        )
        assert model.model_id == "minimal-model"
        assert len(model.states) == 2

    def test_invalid_initial_state_rejected(self):
        with pytest.raises(ValidationError):
            WorkflowModelDefinition(
                model_id="bad-initial",
                version="1.0.0",
                project_id="test-proj",
                domain="e-commerce",
                name="Bad Initial",
                states=[EFSMState(state_id="S1", name="S1")],
                initial_state="NON_EXISTENT",
                transitions=[
                    EFSMTransition(
                        transition_id="T1",
                        source_state="S1",
                        target_state="S1",
                        trigger_event="EV1",
                    )
                ],
            )

    def test_undeclared_transition_state_rejected(self):
        with pytest.raises(ValidationError):
            WorkflowModelDefinition(
                model_id="bad-transition",
                version="1.0.0",
                project_id="test-proj",
                domain="e-commerce",
                name="Bad Transition",
                states=[EFSMState(state_id="START", name="Start")],
                initial_state="START",
                transitions=[
                    EFSMTransition(
                        transition_id="T1",
                        source_state="START",
                        target_state="UNKNOWN_TARGET",
                        trigger_event="EV1",
                    )
                ],
            )

    def test_duplicate_transition_id_rejected(self):
        with pytest.raises(ValidationError):
            WorkflowModelDefinition(
                model_id="duplicate-t-id",
                version="1.0.0",
                project_id="test-proj",
                domain="e-commerce",
                name="Duplicate T",
                states=[
                    EFSMState(state_id="START", name="Start"),
                    EFSMState(state_id="END", name="End"),
                ],
                initial_state="START",
                transitions=[
                    EFSMTransition(
                        transition_id="T1",
                        source_state="START",
                        target_state="END",
                        trigger_event="EV1",
                    ),
                    EFSMTransition(
                        transition_id="T1",
                        source_state="START",
                        target_state="END",
                        trigger_event="EV2",
                    ),
                ],
            )


class TestGeneratedTestAndEvidenceContracts:
    """Tests generated test, runtime evidence, and evaluation result models."""

    def test_generated_workflow_test_instantiation(self):
        fixture = SyntheticFixtureReference(
            fixture_id="FIX-001",
            domain="e-commerce",
            description="Synthetic cart fixture",
            seed=101,
            initial_entities={"orders": [503]},
        )
        test_case = GeneratedWorkflowTest(
            test_id="C2-TEST-001",
            test_version="1.0.0",
            model_id="ecommerce-refund-efsm",
            model_version="1.0.0",
            category=TestCategory.MUTATED,
            task="Refund my latest paid order",
            fixture_reference=fixture,
            seed=101,
            expected_outcome=ExpectedOutcome(
                expected_verdict=EvaluationVerdict.FAIL,
                expected_final_state="S_REFUND_REQUESTED",
            ),
            reference_path=ReferencePathInfo(
                state_sequence=["S_START", "S_REFUND_REQUESTED"],
                transition_sequence=["T1"],
                is_hidden_from_agent=True,
            ),
            mutation_provenance=MutationProvenance(
                mutation_type=MutationType.SKIPPED_STEP,
                original_target_transition="T_IDENTIFY",
                injected_fault_description="Skipped eligibility check",
                label="MUT-SKIP-01",
            ),
            readiness=TestReadiness(status=TestReadinessStatus.READY),
        )
        assert test_case.test_id == "C2-TEST-001"
        assert test_case.category == TestCategory.MUTATED
        assert test_case.reference_path.is_hidden_from_agent is True

    def test_runtime_evidence_and_collection(self):
        now = datetime.now(timezone.utc)
        event = RuntimeEvidenceEvent(
            project_id="proj-1",
            run_id="run-100",
            test_id="test-1",
            event_id="evt-1",
            sequence_index=0,
            tool_call_id="call-abc",
            timestamp=now,
            tool_name="get_orders",
            tool_input={"customer_id": 42},
            tool_output={"orders": [501, 503]},
            entity_ids={"customer_id": 42},
            before_state={"selected_order_id": ObservedValue.missing()},
            after_state={"selected_order_id": ObservedValue.of(503)},
            state_diff={"selected_order_id": {"from": None, "to": 503}},
            evidence_completeness=EvidenceCompletenessInfo(
                status="COMPLETE",
                is_complete=True,
            ),
        )
        trace = WorkflowExecutionEvidence(
            project_id="proj-1",
            run_id="run-100",
            test_id="test-1",
            events=[event],
            total_events=1,
            captured_at=now,
        )
        assert trace.total_events == 1
        assert trace.events[0].before_state["selected_order_id"].is_missing
        assert trace.events[0].after_state["selected_order_id"].value == 503

    def test_evaluation_result_instantiation(self):
        now = datetime.now(timezone.utc)
        result = WorkflowEvaluationResult(
            verdict=EvaluationVerdict.FAIL,
            reason_codes=[ReasonCode.OUTCOME_NOT_MET, ReasonCode.GUARD_VIOLATION],
            model_id="ecommerce-refund-efsm",
            model_version="1.0.0",
            test_id="test-017",
            test_version="1.0.0",
            expected_state_sequence=["S_START", "S_PAID", "S_REFUNDED"],
            observed_state_sequence=["S_START", "S_PAID", "S_TERMINATED"],
            violations=[
                WorkflowViolation(
                    step_index=2,
                    violation_type="GUARD_VIOLATION",
                    rule_id="RULE-REFUND-001",
                    description="Order status was not PAID before refund attempt",
                )
            ],
            first_divergence=FirstDivergenceInfo(
                first_divergence_index=2,
                expected_transition="T3_SUBMIT_REFUND",
                expected_state="S_REFUNDED",
                observed_event="EV_TERMINATED",
                observed_state="S_TERMINATED",
                reason="Agent stopped before initiating refund action",
            ),
            evidence_references=["evt-1", "evt-2"],
            coverage=WorkflowCoverageInfo(
                transitions_covered=["T1", "T2"],
                transitions_total=4,
                transition_coverage_ratio=0.5,
                guards_covered=["G1"],
                guards_total=2,
                guard_coverage_ratio=0.5,
                paths_covered=["P1"],
                state_effects_detected=1,
            ),
            evaluated_at=now,
            evaluation_duration_ms=45.2,
        )
        assert result.verdict == EvaluationVerdict.FAIL
        assert result.first_divergence is not None
        assert result.first_divergence.first_divergence_index == 2

    def test_workflow_input_instantiation(self):
        wf_input = WorkflowInput(
            schema_version="1.0.0",
            project_id="proj-1",
            domain="e-commerce",
            task_description="Test task",
            workflow_rules=[
                WorkflowRule(
                    rule_id="R1",
                    name="Rule 1",
                    description="Desc",
                    rule_type="precondition",
                )
            ],
            tool_specifications=[
                ToolSpecification(
                    tool_name="tool_1",
                    description="Desc",
                    is_state_modifying=False,
                )
            ],
            observable_state_mappings=[
                ObservableStateMapping(
                    entity_name="order",
                    source_table="orders",
                    key_field="id",
                    observable_fields=["status"],
                )
            ],
            fixture_references=[
                SyntheticFixtureReference(
                    fixture_id="FIX-1",
                    domain="e-commerce",
                    description="Fixture",
                )
            ],
        )
        assert wf_input.project_id == "proj-1"
        assert len(wf_input.workflow_rules) == 1

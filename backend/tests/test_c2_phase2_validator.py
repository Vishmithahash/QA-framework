"""Tests for reference model structural and bounded semantic validator."""

from app.components.c2_state_aware_workflow.contracts.efsm import (
    EFSMState,
    EFSMTransition,
    WorkflowModelDefinition,
)
from app.components.c2_state_aware_workflow.contracts.enums import (
    EffectType,
    PredicateOperator,
    ReasonCode,
)
from app.components.c2_state_aware_workflow.contracts.predicates import (
    StateEffectSpec,
    StructuredPredicate,
    VariableUpdate,
)
from app.components.c2_state_aware_workflow.examples.refund_workflow import (
    get_draft_refund_workflow_definition,
)
from app.components.c2_state_aware_workflow.services.model_validator import (
    WorkflowModelValidator,
)


class TestStructuralValidation:
    """Verifies detection of structural flaws in reference models."""

    def test_valid_refund_model_passes_structural_checks(self):
        validator = WorkflowModelValidator()
        model = get_draft_refund_workflow_definition()
        report = validator.validate(model)

        assert report.is_valid is True
        assert report.has_blocking_issues is False
        assert len(report.errors) == 0
        assert "check_duplicate_identifiers" in report.checks_performed
        assert "check_graph_reachability" in report.checks_performed
        assert len(report.checks_not_completed) >= 1

    def test_unreachable_state_detected(self):
        validator = WorkflowModelValidator()
        model = get_draft_refund_workflow_definition()

        # Add isolated state with no incoming transitions
        states = list(model.states)
        states.append(
            EFSMState(
                state_id="S_ORPHAN",
                name="Orphan State",
                is_initial=False,
                is_accepting=False,
            )
        )
        model = model.model_copy(update={"states": states})

        report = validator.validate(model)
        assert report.is_valid is False
        assert report.has_blocking_issues is True

        orphan_err = next(
            (e for e in report.errors if e.affected_element_id == "S_ORPHAN"), None
        )
        assert orphan_err is not None
        assert (
            orphan_err.issue_code == ReasonCode.MODEL_NOT_READY_UNREACHABLE_STATE.value
        )

    def test_nonterminal_dead_end_detected(self):
        validator = WorkflowModelValidator()
        model = get_draft_refund_workflow_definition()

        # Add state reachable from start, but with NO outgoing transitions and NOT terminal
        states = list(model.states)
        states.append(
            EFSMState(
                state_id="S_TRAP",
                name="Trap State",
                is_initial=False,
                is_accepting=False,
                is_expected_rejection=False,
            )
        )
        transitions = list(model.transitions)
        transitions.append(
            EFSMTransition(
                transition_id="T_TO_TRAP",
                source_state="S_START",
                target_state="S_TRAP",
                trigger_event="EV_GO_TRAP",
            )
        )
        model = model.model_copy(update={"states": states, "transitions": transitions})

        report = validator.validate(model)
        assert report.is_valid is False
        trap_err = next(
            (e for e in report.errors if e.affected_element_id == "S_TRAP"), None
        )
        assert trap_err is not None
        assert trap_err.issue_code == ReasonCode.MODEL_NOT_READY_DEAD_END.value

    def test_dangling_transitions_detected(self):
        validator = WorkflowModelValidator()
        model = get_draft_refund_workflow_definition()

        new_transitions = list(model.transitions) + [
            EFSMTransition(
                transition_id="T_DANGLING",
                source_state="S_START",
                target_state="S_NONEXISTENT_TARGET",
                trigger_event="EV_DUMMY",
            )
        ]
        # Bypassing model_validator on WorkflowModelDefinition to test validator layer
        fields = {k: getattr(model, k) for k in WorkflowModelDefinition.model_fields}
        fields["transitions"] = new_transitions
        model_obj = WorkflowModelDefinition.model_construct(**fields)

        report = validator.validate(model_obj)
        assert report.is_valid is False
        assert any(e.issue_code == "DANGLING_TRANSITION_TARGET" for e in report.errors)

    def test_contradictory_terminal_state_detected(self):
        validator = WorkflowModelValidator()
        model = get_draft_refund_workflow_definition()
        # Make a state both accepting and expected rejection
        model_obj = model.model_copy(
            update={"expected_rejection_states": ["S_REFUNDED"]}
        )

        report = validator.validate(model_obj)
        assert report.is_valid is False
        assert any(
            e.issue_code == "CONTRADICTORY_TERMINAL_STATE" for e in report.errors
        )


class TestBoundedSemanticValidation:
    """Verifies bounded semantic checks within declared finite variable and fixture domains."""

    def test_infeasible_guard_detected(self):
        validator = WorkflowModelValidator()
        model = get_draft_refund_workflow_definition()

        # Update guard on T2 to require selected_order_id == 9999 (not in declared domain [501, 503])
        transitions = []
        for t in model.transitions:
            if t.transition_id == "T2_IDENTIFY_LATEST_ORDER":
                new_guards = list(t.guards)
                new_guards.append(
                    StructuredPredicate(
                        field="selected_order_id",
                        operator=PredicateOperator.EQ,
                        value=9999,  # Infeasible!
                    )
                )
                transitions.append(t.model_copy(update={"guards": new_guards}))
            else:
                transitions.append(t)

        model_infeasible = model.model_copy(update={"transitions": transitions})
        report = validator.validate(model_infeasible)

        assert report.is_valid is False
        assert any(
            e.issue_code == ReasonCode.MODEL_NOT_READY_INFEASIBLE_GUARD.value
            for e in report.errors
        )

    def test_contradictory_guards_on_same_transition_detected(self):
        validator = WorkflowModelValidator()
        model = get_draft_refund_workflow_definition()

        # Add mutually contradictory equality guards: status == "PAID" and status == "UNPAID"
        transitions = []
        for t in model.transitions:
            if t.transition_id == "T1_RETRIEVE_PAID_ORDERS":
                guards = [
                    StructuredPredicate(
                        field="customer_id", operator=PredicateOperator.EQ, value=42
                    ),
                    StructuredPredicate(
                        field="customer_id", operator=PredicateOperator.EQ, value=99
                    ),
                ]
                transitions.append(t.model_copy(update={"guards": guards}))
            else:
                transitions.append(t)

        model_contradictory = model.model_copy(update={"transitions": transitions})
        report = validator.validate(model_contradictory)

        assert report.is_valid is False
        assert any(
            e.issue_code == ReasonCode.MODEL_NOT_READY_CONTRADICTORY_RULES.value
            for e in report.errors
        )

    def test_conflicting_variable_updates_detected(self):
        validator = WorkflowModelValidator()
        model = get_draft_refund_workflow_definition()

        transitions = []
        for t in model.transitions:
            if t.transition_id == "T2_IDENTIFY_LATEST_ORDER":
                upds = list(t.variable_updates)
                upds.append(
                    VariableUpdate(
                        variable_name="selected_order_status",
                        operation="set",
                        value="CONFLICTING_STATUS",
                    )
                )
                transitions.append(t.model_copy(update={"variable_updates": upds}))
            else:
                transitions.append(t)

        model_conflict = model.model_copy(update={"transitions": transitions})
        report = validator.validate(model_conflict)

        assert report.is_valid is False
        assert any(
            e.issue_code == "CONFLICTING_VARIABLE_UPDATES" for e in report.errors
        )

    def test_invariant_and_effect_contradiction_detected(self):
        validator = WorkflowModelValidator()
        model = get_draft_refund_workflow_definition()

        # Invariant says selected_order_status != "UNPAID" at S_REFUNDED
        # Add transition update that sets selected_order_status = "UNPAID" on entering S_REFUNDED
        transitions = []
        for t in model.transitions:
            if t.transition_id == "T4_CONFIRM_REFUND_SUCCESS":
                upds = [
                    VariableUpdate(
                        variable_name="selected_order_status",
                        operation="set",
                        value="UNPAID",  # Directly violates invariant!
                    )
                ]
                transitions.append(t.model_copy(update={"variable_updates": upds}))
            else:
                transitions.append(t)

        model_inv_violated = model.model_copy(update={"transitions": transitions})
        report = validator.validate(model_inv_violated)

        assert report.is_valid is False
        assert any(
            e.issue_code == ReasonCode.MODEL_NOT_READY_CONTRADICTORY_RULES.value
            for e in report.errors
        )

    def test_rejection_path_mutating_state_effect_blocked(self):
        validator = WorkflowModelValidator()
        model = get_draft_refund_workflow_definition()

        # T5 targets S_REFUND_REJECTED. Add a mutating CREATED effect to it!
        transitions = []
        for t in model.transitions:
            if t.transition_id == "T5_REJECT_INVALID_REFUND":
                illegal_effects = [
                    StateEffectSpec(
                        entity_type="order",
                        entity_id_var="selected_order_id",
                        field="payment_status",
                        effect_type=EffectType.UPDATED,  # Mutating effect forbidden on rejection!
                        expected_value="ILLEGALLY_MODIFIED",
                    )
                ]
                transitions.append(
                    t.model_copy(update={"expected_state_effects": illegal_effects})
                )
            else:
                transitions.append(t)

        model_rejection_mutating = model.model_copy(update={"transitions": transitions})
        report = validator.validate(model_rejection_mutating)

        assert report.is_valid is False
        assert any(
            e.issue_code == ReasonCode.MODEL_NOT_READY_PROTECTED_STATE_VIOLATION.value
            for e in report.errors
        )

    def test_permitted_alternative_path_is_warning_not_blocking(self):
        validator = WorkflowModelValidator()
        model = get_draft_refund_workflow_definition()

        report = validator.validate(model)
        # Should be valid despite alternative path T4_ALT_SYNCHRONOUS_REFUND sharing event with T4
        assert report.is_valid is True
        assert report.has_blocking_issues is False
        alt_warning = next(
            (
                w
                for w in report.warnings
                if w.issue_code == "PERMITTED_ALTERNATIVE_PATH"
            ),
            None,
        )
        assert alt_warning is not None
        assert alt_warning.is_blocking is False

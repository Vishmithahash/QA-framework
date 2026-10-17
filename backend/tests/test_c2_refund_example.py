"""Tests for the synthetic draft refund workflow example."""

from app.components.c2_state_aware_workflow.contracts.enums import (
    EffectType,
    PredicateOperator,
)
from app.components.c2_state_aware_workflow.examples.refund_workflow import (
    STATE_LATEST_ORDER_IDENTIFIED,
    STATE_PAID_ORDERS_RETRIEVED,
    STATE_REFUND_REJECTED,
    STATE_REFUND_REQUESTED,
    STATE_REFUNDED,
    STATE_START,
    get_draft_refund_create_request,
    get_draft_refund_workflow_definition,
    get_draft_refund_workflow_input,
)


class TestRefundWorkflowExample:
    """Validates the synthetic 'Refund my latest paid order' draft EFSM."""

    def test_workflow_definition_structure(self):
        efsm = get_draft_refund_workflow_definition()

        # States check
        state_ids = [s.state_id for s in efsm.states]
        assert state_ids == [
            STATE_START,
            STATE_PAID_ORDERS_RETRIEVED,
            STATE_LATEST_ORDER_IDENTIFIED,
            STATE_REFUND_REQUESTED,
            STATE_REFUNDED,
            STATE_REFUND_REJECTED,
        ]
        assert efsm.initial_state == STATE_START
        assert efsm.accepting_states == [STATE_REFUNDED]
        assert efsm.expected_rejection_states == [STATE_REFUND_REJECTED]

    def test_synthetic_entities_and_variables(self):
        efsm = get_draft_refund_workflow_definition()
        var_map = {v.name: v for v in efsm.variables}

        assert "customer_id" in var_map
        assert 42 in var_map["customer_id"].declared_input_domain

        assert "selected_order_id" in var_map
        assert 501 in var_map["selected_order_id"].declared_input_domain
        assert 503 in var_map["selected_order_id"].declared_input_domain

        assert "selected_order_status" in var_map
        assert "PAID" in var_map["selected_order_status"].declared_input_domain

    def test_conceptual_workflow_transitions(self):
        efsm = get_draft_refund_workflow_definition()
        t_map = {t.transition_id: t for t in efsm.transitions}

        # Step 1: Start -> Paid Orders Retrieved
        t1 = t_map["T1_RETRIEVE_PAID_ORDERS"]
        assert t1.source_state == STATE_START
        assert t1.target_state == STATE_PAID_ORDERS_RETRIEVED

        # Step 2: Paid Orders Retrieved -> Latest Eligible Order Identified
        t2 = t_map["T2_IDENTIFY_LATEST_ORDER"]
        assert t2.source_state == STATE_PAID_ORDERS_RETRIEVED
        assert t2.target_state == STATE_LATEST_ORDER_IDENTIFIED
        # Explicit latest ordering rule: order 503 selected
        has_503_guard = any(
            g.field == "selected_order_id"
            and g.operator == PredicateOperator.EQ
            and g.value == 503
            for g in t2.guards
        )
        assert has_503_guard

        # Step 3: Latest Eligible Order Identified -> Refund Requested
        t3 = t_map["T3_SUBMIT_REFUND_REQUEST"]
        assert t3.source_state == STATE_LATEST_ORDER_IDENTIFIED
        assert t3.target_state == STATE_REFUND_REQUESTED

        # Step 4: Refund Requested -> Refunded
        t4 = t_map["T4_CONFIRM_REFUND_SUCCESS"]
        assert t4.source_state == STATE_REFUND_REQUESTED
        assert t4.target_state == STATE_REFUNDED

        # Step 5: Rejection transition for invalid/unpaid request
        t5 = t_map["T5_REJECT_INVALID_REFUND"]
        assert t5.source_state == STATE_PAID_ORDERS_RETRIEVED
        assert t5.target_state == STATE_REFUND_REJECTED

    def test_entity_continuity_rule(self):
        efsm = get_draft_refund_workflow_definition()
        assert len(efsm.entity_bindings) == 1
        rule = efsm.entity_bindings[0]
        assert rule.primary_key_var == "selected_order_id"
        assert rule.continuous_across_states == [
            STATE_LATEST_ORDER_IDENTIFIED,
            STATE_REFUND_REQUESTED,
            STATE_REFUNDED,
        ]

    def test_invariants_and_protected_fields(self):
        efsm = get_draft_refund_workflow_definition()
        inv_map = {inv.invariant_id: inv for inv in efsm.invariants}
        assert "INV_NO_UNPAID_REFUND" in inv_map

        protected_names = {pf.field_name for pf in efsm.protected_fields}
        assert "order_501_payment_status" in protected_names
        assert "customer_42_email" in protected_names

    def test_expected_state_effects(self):
        efsm = get_draft_refund_workflow_definition()
        effects = efsm.expected_state_effects
        effect_entities = {e.entity_type for e in effects}
        assert "refund" in effect_entities
        assert "order" in effect_entities

        order_effect = next(e for e in effects if e.entity_type == "order")
        assert order_effect.effect_type == EffectType.UPDATED
        assert order_effect.expected_value == "REFUNDED"

    def test_workflow_input_matches_fixture_and_tools(self):
        wf_input = get_draft_refund_workflow_input()
        assert wf_input.task_description == "Refund my latest paid order."
        assert len(wf_input.tool_specifications) == 4
        assert len(wf_input.fixture_references) == 1
        fixture = wf_input.fixture_references[0]
        assert fixture.fixture_id == "FIX-ECOMMERCE-REFUND-042"
        assert fixture.initial_entities["customer"]["id"] == 42
        order_ids = [o["id"] for o in fixture.initial_entities["orders"]]
        assert order_ids == [501, 503, 502]

    def test_create_request_matches_definition(self):
        req = get_draft_refund_create_request()
        assert req.project_id == "nexacart-qa-synthetic"
        assert req.definition.model_id == "ecommerce-refund-latest-paid"

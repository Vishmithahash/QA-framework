"""Synthetic, draft EFSM example: 'Refund my latest paid order'.

Domain assumptions explicitly labelled:
- Domain: e-commerce (synthetic, abstract models; no actual NexaCart endpoints or live schemas invented).
- Customer ID: 42 (the authenticated requesting customer).
- Older paid order ID: 501 (created at 2026-10-01, status PAID, amount 45.00).
- Later paid order ID: 503 (created at 2026-10-10, status PAID, amount 89.00).
- Unpaid order ID: 502 (status UNPAID, used for testing negative rejection paths).
- Ordering Rule: Explicit latest ordering rule selects order 503 over 501 because created_at(503) > created_at(501).
- Entity Continuity: The order selected as latest eligible (503) must be the same order submitted for refund and verified afterwards.
- Invariant: A refund must never be completed for an unpaid order.
- Expected State Effects: Refund record created with status 'COMPLETED'; order payment status updated to 'REFUNDED'.
- Protected State: Customer profile attributes and older order 501 remain unchanged.
- Status: Strictly DRAFT (per Phase 1 requirement).
"""

from app.components.c2_state_aware_workflow.contracts.efsm import (
    EFSMState,
    EFSMTransition,
    EFSMVariable,
    EntityContinuityRule,
    FinalOutcomeCondition,
    ObservableEventMapping,
    ProtectedField,
    WorkflowInvariant,
    WorkflowMilestone,
    WorkflowModelDefinition,
)
from app.components.c2_state_aware_workflow.contracts.enums import (
    EffectType,
    PredicateOperator,
)
from app.components.c2_state_aware_workflow.contracts.predicates import (
    StateEffectSpec,
    StructuredPredicate,
    VariableUpdate,
)
from app.components.c2_state_aware_workflow.contracts.workflow_input import (
    ObservableStateMapping,
    SyntheticFixtureReference,
    ToolSpecification,
    WorkflowInput,
    WorkflowRule,
)
from app.components.c2_state_aware_workflow.schemas.api_models import (
    CreateDraftWorkflowModelRequest,
)

# State IDs
STATE_START = "S_START"
STATE_PAID_ORDERS_RETRIEVED = "S_PAID_ORDERS_RETRIEVED"
STATE_LATEST_ORDER_IDENTIFIED = "S_LATEST_ORDER_IDENTIFIED"
STATE_REFUND_REQUESTED = "S_REFUND_REQUESTED"
STATE_REFUNDED = "S_REFUNDED"
STATE_REFUND_REJECTED = "S_REFUND_REJECTED"


def get_draft_refund_workflow_definition() -> WorkflowModelDefinition:
    """Returns the validated EFSM behavioral reference definition for the refund workflow."""
    return WorkflowModelDefinition(
        model_id="ecommerce-refund-latest-paid",
        version="1.0.0",
        schema_version="1.0.0",
        project_id="nexacart-qa-synthetic",
        domain="e-commerce",
        name="Refund Latest Paid Order Workflow",
        description=(
            "Synthetic behavioral EFSM oracle for 'Refund my latest paid order'. "
            "Enforces customer ownership (42), chronological ordering (503 > 501), "
            "entity continuity, unpaid refund prevention, and protected state immutability."
        ),
        states=[
            EFSMState(
                state_id=STATE_START,
                name="Start",
                description="Workflow initiated; initial state",
                is_initial=True,
                is_accepting=False,
                is_expected_rejection=False,
            ),
            EFSMState(
                state_id=STATE_PAID_ORDERS_RETRIEVED,
                name="Paid Orders Retrieved",
                description="Customer orders retrieved and filtered for paid status",
                is_initial=False,
                is_accepting=False,
                is_expected_rejection=False,
            ),
            EFSMState(
                state_id=STATE_LATEST_ORDER_IDENTIFIED,
                name="Latest Eligible Order Identified",
                description="Chronologically latest paid order (503) identified and bound",
                is_initial=False,
                is_accepting=False,
                is_expected_rejection=False,
            ),
            EFSMState(
                state_id=STATE_REFUND_REQUESTED,
                name="Refund Requested",
                description="Refund API action initiated for the bound order",
                is_initial=False,
                is_accepting=False,
                is_expected_rejection=False,
            ),
            EFSMState(
                state_id=STATE_REFUNDED,
                name="Refunded",
                description="Refund successfully confirmed and order state updated; accepting state",
                is_initial=False,
                is_accepting=True,
                is_expected_rejection=False,
            ),
            EFSMState(
                state_id=STATE_REFUND_REJECTED,
                name="Refund Rejected",
                description="Invalid refund request safely rejected while state is preserved",
                is_initial=False,
                is_accepting=False,
                is_expected_rejection=True,
            ),
        ],
        initial_state=STATE_START,
        accepting_states=[STATE_REFUNDED],
        expected_rejection_states=[STATE_REFUND_REJECTED],
        variables=[
            EFSMVariable(
                name="customer_id",
                var_type="int",
                declared_input_domain=[42],
                initial_value=42,
                description="Requesting customer identifier",
            ),
            EFSMVariable(
                name="selected_order_id",
                var_type="int",
                declared_input_domain=[501, 503],
                initial_value=None,
                description="Primary order entity bound across workflow steps",
            ),
            EFSMVariable(
                name="selected_order_status",
                var_type="str",
                declared_input_domain=["PAID", "UNPAID", "REFUNDED"],
                initial_value=None,
                description="Payment status of the selected order",
            ),
            EFSMVariable(
                name="refund_id",
                var_type="str",
                declared_input_domain=[],
                initial_value=None,
                description="Refund record ID generated upon refund creation",
            ),
        ],
        transitions=[
            EFSMTransition(
                transition_id="T1_RETRIEVE_PAID_ORDERS",
                source_state=STATE_START,
                target_state=STATE_PAID_ORDERS_RETRIEVED,
                trigger_event="EV_ORDERS_RETRIEVED",
                description="Query orders for customer 42",
                guards=[
                    StructuredPredicate(
                        field="customer_id",
                        operator=PredicateOperator.EQ,
                        value=42,
                    )
                ],
                variable_updates=[],
                expected_state_effects=[],
            ),
            EFSMTransition(
                transition_id="T2_IDENTIFY_LATEST_ORDER",
                source_state=STATE_PAID_ORDERS_RETRIEVED,
                target_state=STATE_LATEST_ORDER_IDENTIFIED,
                trigger_event="EV_LATEST_ORDER_SELECTED",
                description="Select order 503 because it is chronologically later than order 501",
                guards=[
                    StructuredPredicate(
                        field="customer_id",
                        operator=PredicateOperator.EQ,
                        value=42,
                    ),
                    StructuredPredicate(
                        field="selected_order_id",
                        operator=PredicateOperator.EQ,
                        value=503,
                    ),
                    StructuredPredicate(
                        field="selected_order_status",
                        operator=PredicateOperator.EQ,
                        value="PAID",
                    ),
                ],
                variable_updates=[
                    VariableUpdate(
                        variable_name="selected_order_id",
                        operation="bind_entity",
                        value=503,
                    ),
                    VariableUpdate(
                        variable_name="selected_order_status",
                        operation="set",
                        value="PAID",
                    ),
                ],
                expected_state_effects=[],
            ),
            EFSMTransition(
                transition_id="T3_SUBMIT_REFUND_REQUEST",
                source_state=STATE_LATEST_ORDER_IDENTIFIED,
                target_state=STATE_REFUND_REQUESTED,
                trigger_event="EV_REFUND_REQUESTED",
                description="Submit refund request for bound order 503",
                guards=[
                    StructuredPredicate(
                        field="selected_order_id",
                        operator=PredicateOperator.EQ,
                        value=503,
                    ),
                    StructuredPredicate(
                        field="selected_order_status",
                        operator=PredicateOperator.EQ,
                        value="PAID",
                    ),
                ],
                variable_updates=[],
                expected_state_effects=[],
            ),
            EFSMTransition(
                transition_id="T4_CONFIRM_REFUND_SUCCESS",
                source_state=STATE_REFUND_REQUESTED,
                target_state=STATE_REFUNDED,
                trigger_event="EV_REFUND_CONFIRMED",
                description="Verify refund record created and order status updated to REFUNDED",
                guards=[
                    StructuredPredicate(
                        field="selected_order_id",
                        operator=PredicateOperator.EQ,
                        value=503,
                    ),
                ],
                variable_updates=[
                    VariableUpdate(
                        variable_name="selected_order_status",
                        operation="set",
                        value="REFUNDED",
                    )
                ],
                expected_state_effects=[
                    StateEffectSpec(
                        entity_type="refund",
                        entity_id_var="selected_order_id",
                        field="status",
                        effect_type=EffectType.CREATED,
                        expected_value="COMPLETED",
                        description="Refund record must be created with status COMPLETED",
                    ),
                    StateEffectSpec(
                        entity_type="order",
                        entity_id_var="selected_order_id",
                        field="payment_status",
                        effect_type=EffectType.UPDATED,
                        expected_value="REFUNDED",
                        description="Order payment status must be updated to REFUNDED",
                    ),
                ],
            ),
            EFSMTransition(
                transition_id="T5_REJECT_INVALID_REFUND",
                source_state=STATE_PAID_ORDERS_RETRIEVED,
                target_state=STATE_REFUND_REJECTED,
                trigger_event="EV_REFUND_REJECTED",
                description="Reject refund for unpaid or ineligible order with state preserved",
                guards=[
                    StructuredPredicate(
                        field="selected_order_status",
                        operator=PredicateOperator.NEQ,
                        value="PAID",
                    )
                ],
                variable_updates=[],
                expected_state_effects=[
                    StateEffectSpec(
                        entity_type="order",
                        entity_id_var="selected_order_id",
                        field="payment_status",
                        effect_type=EffectType.UNCHANGED,
                        expected_value=None,
                        description="Order status must remain unchanged when rejected",
                    )
                ],
            ),
        ],
        observable_event_mappings=[
            ObservableEventMapping(
                event_name="EV_ORDERS_RETRIEVED",
                tool_name="list_customer_orders",
                result_pattern=None,
                extracted_fields={"customer_id": "customer_id"},
            ),
            ObservableEventMapping(
                event_name="EV_LATEST_ORDER_SELECTED",
                tool_name="select_order_for_action",
                result_pattern=None,
                extracted_fields={"selected_order_id": "order_id"},
            ),
            ObservableEventMapping(
                event_name="EV_REFUND_REQUESTED",
                tool_name="request_order_refund",
                result_pattern=None,
                extracted_fields={"selected_order_id": "order_id"},
            ),
            ObservableEventMapping(
                event_name="EV_REFUND_CONFIRMED",
                tool_name="check_refund_status",
                result_pattern=None,
                extracted_fields={"refund_id": "refund_id"},
            ),
            ObservableEventMapping(
                event_name="EV_REFUND_REJECTED",
                tool_name="request_order_refund",
                result_pattern=".*error|rejected.*",
                extracted_fields={},
            ),
        ],
        invariants=[
            WorkflowInvariant(
                invariant_id="INV_NO_UNPAID_REFUND",
                name="No Refund for Unpaid Orders",
                description="A refund must never be completed if the order payment status was not PAID.",
                scope="state",
                target_scope_id=STATE_REFUNDED,
                predicate=StructuredPredicate(
                    field="selected_order_status",
                    operator=PredicateOperator.NEQ,
                    value="UNPAID",
                ),
            )
        ],
        milestones=[
            WorkflowMilestone(
                milestone_id="MS_ORDERS_FETCHED",
                name="Orders Fetched",
                required_order=1,
                state_or_event=STATE_PAID_ORDERS_RETRIEVED,
                description="Orders queried from customer history",
            ),
            WorkflowMilestone(
                milestone_id="MS_LATEST_ORDER_IDENTIFIED",
                name="Latest Eligible Order Selected",
                required_order=2,
                state_or_event=STATE_LATEST_ORDER_IDENTIFIED,
                description="Order 503 identified via latest ordering rule",
            ),
            WorkflowMilestone(
                milestone_id="MS_REFUND_SUBMITTED",
                name="Refund Request Submitted",
                required_order=3,
                state_or_event=STATE_REFUND_REQUESTED,
                description="Refund request initiated",
            ),
            WorkflowMilestone(
                milestone_id="MS_REFUND_CONFIRMED",
                name="Refund Confirmed",
                required_order=4,
                state_or_event=STATE_REFUNDED,
                description="Refund completed and state validated",
            ),
        ],
        entity_bindings=[
            EntityContinuityRule(
                rule_id="ECR_ORDER_503_CONTINUITY",
                entity_type="order",
                primary_key_var="selected_order_id",
                continuous_across_states=[
                    STATE_LATEST_ORDER_IDENTIFIED,
                    STATE_REFUND_REQUESTED,
                    STATE_REFUNDED,
                ],
                description=(
                    "The order selected as latest eligible (503) must be the exact order "
                    "submitted for refund and verified in the refund record without entity switching."
                ),
            )
        ],
        expected_state_effects=[
            StateEffectSpec(
                entity_type="refund",
                entity_id_var="selected_order_id",
                field="status",
                effect_type=EffectType.CREATED,
                expected_value="COMPLETED",
                description="Refund record created for order 503",
            ),
            StateEffectSpec(
                entity_type="order",
                entity_id_var="selected_order_id",
                field="payment_status",
                effect_type=EffectType.UPDATED,
                expected_value="REFUNDED",
                description="Order 503 status transitioned to REFUNDED",
            ),
        ],
        protected_fields=[
            ProtectedField(
                entity_type="order",
                field_name="order_501_payment_status",
                reason="Older paid order 501 must remain completely unaffected with status PAID",
            ),
            ProtectedField(
                entity_type="customer",
                field_name="customer_42_email",
                reason="Customer profile data must remain immutable during refund execution",
            ),
        ],
        final_outcome_conditions=[
            FinalOutcomeCondition(
                condition_id="FOC_REFUND_SUCCESS",
                outcome_type="ACCEPT",
                description="Order 503 is successfully refunded and recorded",
                predicate=StructuredPredicate(
                    field="selected_order_status",
                    operator=PredicateOperator.EQ,
                    value="REFUNDED",
                ),
            ),
            FinalOutcomeCondition(
                condition_id="FOC_REFUND_SAFE_REJECTION",
                outcome_type="REJECT",
                description="Ineligible request safely rejected with protected state preserved",
                predicate=StructuredPredicate(
                    field="selected_order_status",
                    operator=PredicateOperator.NEQ,
                    value="REFUNDED",
                ),
            ),
        ],
    )


def get_draft_refund_workflow_input() -> WorkflowInput:
    """Returns the WorkflowInput specification for the draft refund workflow."""
    return WorkflowInput(
        schema_version="1.0.0",
        project_id="nexacart-qa-synthetic",
        domain="e-commerce",
        task_description="Refund my latest paid order.",
        workflow_rules=[
            WorkflowRule(
                rule_id="RULE-CUSTOMER-OWNERSHIP",
                name="Customer Ownership",
                description="The selected order must belong to the requesting customer (customer 42).",
                rule_type="precondition",
                predicate=StructuredPredicate(
                    field="customer_id",
                    operator=PredicateOperator.EQ,
                    value=42,
                ),
            ),
            WorkflowRule(
                rule_id="RULE-LATEST-ORDERING",
                name="Latest Chronological Order",
                description="The latest order is determined by chronological created_at timestamp (503 > 501).",
                rule_type="ordering",
                predicate=StructuredPredicate(
                    field="selected_order_id",
                    operator=PredicateOperator.EQ,
                    value=503,
                ),
            ),
            WorkflowRule(
                rule_id="RULE-PAID-STATUS-REQUIRED",
                name="Paid Status Precondition",
                description="Only orders with payment status PAID are eligible for refund.",
                rule_type="precondition",
                predicate=StructuredPredicate(
                    field="selected_order_status",
                    operator=PredicateOperator.EQ,
                    value="PAID",
                ),
            ),
            WorkflowRule(
                rule_id="RULE-ENTITY-CONTINUITY",
                name="Order Entity Continuity",
                description="The order identified as latest must match the refunded order across all steps.",
                rule_type="invariant",
            ),
            WorkflowRule(
                rule_id="RULE-UNPAID-REJECTION",
                name="Unpaid Order Rejection",
                description="An unpaid order refund request must be rejected and protected state preserved.",
                rule_type="rejection",
            ),
        ],
        tool_specifications=[
            ToolSpecification(
                tool_name="list_customer_orders",
                description="Lists orders for customer with order IDs, timestamps, and payment statuses",
                parameters_schema={
                    "type": "object",
                    "properties": {"customer_id": {"type": "integer"}},
                    "required": ["customer_id"],
                },
                is_state_modifying=False,
                observable_events=["EV_ORDERS_RETRIEVED"],
            ),
            ToolSpecification(
                tool_name="select_order_for_action",
                description="Selects an order for further workflow processing",
                parameters_schema={
                    "type": "object",
                    "properties": {"order_id": {"type": "integer"}},
                    "required": ["order_id"],
                },
                is_state_modifying=False,
                observable_events=["EV_LATEST_ORDER_SELECTED"],
            ),
            ToolSpecification(
                tool_name="request_order_refund",
                description="Submits a refund request for the specified order",
                parameters_schema={
                    "type": "object",
                    "properties": {"order_id": {"type": "integer"}},
                    "required": ["order_id"],
                },
                is_state_modifying=True,
                observable_events=["EV_REFUND_REQUESTED", "EV_REFUND_REJECTED"],
            ),
            ToolSpecification(
                tool_name="check_refund_status",
                description="Verifies the status of a submitted refund",
                parameters_schema={
                    "type": "object",
                    "properties": {"order_id": {"type": "integer"}},
                    "required": ["order_id"],
                },
                is_state_modifying=False,
                observable_events=["EV_REFUND_CONFIRMED"],
            ),
        ],
        observable_state_mappings=[
            ObservableStateMapping(
                entity_name="order",
                source_table="orders",
                key_field="id",
                observable_fields=[
                    "customer_id",
                    "payment_status",
                    "created_at",
                    "total_amount",
                ],
                description="Order database record tracking lifecycle and payment status",
            ),
            ObservableStateMapping(
                entity_name="refund",
                source_table="refunds",
                key_field="id",
                observable_fields=["order_id", "status", "created_at"],
                description="Refund record tracking refund execution",
            ),
        ],
        fixture_references=[
            SyntheticFixtureReference(
                fixture_id="FIX-ECOMMERCE-REFUND-042",
                domain="e-commerce",
                description=(
                    "Synthetic fixture with Customer 42, older paid order 501 ($45.00), "
                    "later paid order 503 ($89.00), and unpaid order 502."
                ),
                seed=4242,
                initial_entities={
                    "customer": {"id": 42, "email": "customer42@synthetic.test"},
                    "orders": [
                        {
                            "id": 501,
                            "customer_id": 42,
                            "payment_status": "PAID",
                            "created_at": "2026-10-01T10:00:00Z",
                        },
                        {
                            "id": 503,
                            "customer_id": 42,
                            "payment_status": "PAID",
                            "created_at": "2026-10-10T14:30:00Z",
                        },
                        {
                            "id": 502,
                            "customer_id": 42,
                            "payment_status": "UNPAID",
                            "created_at": "2026-10-11T09:00:00Z",
                        },
                    ],
                },
                reset_hook="/api/v1/fixtures/ecommerce/reset",
            )
        ],
    )


def get_draft_refund_create_request() -> CreateDraftWorkflowModelRequest:
    """Returns the API payload for creating the draft refund workflow model."""
    definition = get_draft_refund_workflow_definition()
    return CreateDraftWorkflowModelRequest(
        project_id=definition.project_id,
        domain=definition.domain,
        name=definition.name,
        description=definition.description,
        definition=definition,
    )

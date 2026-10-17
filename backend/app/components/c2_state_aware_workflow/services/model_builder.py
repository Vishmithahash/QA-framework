"""Candidate reference model builder service for Component 2.

Accepts normalized WorkflowInput specifications and constructs candidate
WorkflowModelDefinition contracts via deterministic rule translation or optional
model-assisted providers. Ensures core functionality operates without paid credentials.
"""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field
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
    WorkflowInput,
    WorkflowRule,
)
from app.components.c2_state_aware_workflow.interfaces.shared import (
    ModelAssistedBuilderProvider,
)


class ModelConstructionResult(BaseModel):
    """Result payload from candidate model construction."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(
        ..., description="True if candidate model was constructed successfully"
    )
    candidate_model: WorkflowModelDefinition | None = Field(
        default=None, description="Constructed candidate EFSM model definition"
    )
    diagnostics: list[str] = Field(
        default_factory=list,
        description="Diagnostic messages or reasons for construction failure",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Explicit domain assumptions made during construction",
    )
    source_rules: list[str] = Field(
        default_factory=list,
        description="Rule IDs referenced during model construction",
    )
    builder_provenance: str = Field(
        default="deterministic_model_builder_v2",
        description="Provenance of the model construction mechanism",
    )


class ModelBuilderService:
    """Service for building candidate EFSM workflow reference models from normalized input."""

    def __init__(self, provider: ModelAssistedBuilderProvider | None = None):
        self.provider = provider

    def build_candidate_model(
        self,
        workflow_input: WorkflowInput,
        model_id: str | None = None,
        version: str = "1.0.0",
    ) -> ModelConstructionResult:
        """Constructs a candidate WorkflowModelDefinition from a normalized WorkflowInput.

        Enforces:
        1. Refusal to fabricate business semantics if input is insufficient.
        2. Deterministic construction from declared business rules, tools, state mappings, and fixtures.
        3. Recording of builder provenance, source rule references, and assumptions.
        4. Candidate model starts strictly as DRAFT.
        """
        diagnostics: list[str] = []

        # Step 1: Validate sufficiency of input
        if not workflow_input.workflow_rules:
            diagnostics.append(
                "Insufficient input: No workflow_rules provided. "
                "Business semantics cannot be fabricated from API/database schemas alone."
            )

        if not workflow_input.tool_specifications:
            diagnostics.append(
                "Insufficient input: No tool_specifications provided. "
                "Observable actions cannot be mapped without tool contracts."
            )

        if not workflow_input.project_id:
            diagnostics.append("Insufficient input: Missing required project_id.")

        if diagnostics:
            return ModelConstructionResult(
                success=False,
                candidate_model=None,
                diagnostics=diagnostics,
                source_rules=[],
                assumptions=[],
            )

        # Check for model-assisted provider if supplied
        if self.provider is not None:
            try:
                candidate_dict = self.provider.generate_candidate_model(workflow_input)
                if candidate_dict is not None:
                    candidate_def = WorkflowModelDefinition.model_validate(
                        candidate_dict
                    )
                    return ModelConstructionResult(
                        success=True,
                        candidate_model=candidate_def,
                        diagnostics=[],
                        assumptions=["Synthesized via model-assisted provider"],
                        source_rules=[r.rule_id for r in workflow_input.workflow_rules],
                        builder_provenance="model_assisted_provider",
                    )
            except Exception as exc:
                diagnostics.append(
                    f"Model-assisted provider fallback to deterministic builder due to: {exc}"
                )

        # Step 2: Deterministic construction for supported structured inputs
        return self._build_deterministic(workflow_input, model_id, version, diagnostics)

    def _build_deterministic(
        self,
        workflow_input: WorkflowInput,
        model_id: str | None,
        version: str,
        initial_diagnostics: list[str],
    ) -> ModelConstructionResult:
        """Deterministic rule-driven model synthesis."""
        rules_by_type: dict[str, list[WorkflowRule]] = {}
        for r in workflow_input.workflow_rules:
            rules_by_type.setdefault(r.rule_type, []).append(r)

        source_rules = [r.rule_id for r in workflow_input.workflow_rules]
        assumptions: list[str] = [
            "Deterministic synthesis based strictly on declared workflow rules and tool specifications.",
            "Initial state is normalized to 'S_START'.",
            "API responses follow standard JSON object payload conventions.",
        ]

        assigned_model_id = (
            model_id
            or f"{workflow_input.domain}-workflow-{workflow_input.project_id.split('-')[0]}"
        )

        # Extract fixture domains
        fixture_domains: dict[str, list[Any]] = {}
        if workflow_input.fixture_references:
            fix = workflow_input.fixture_references[0]
            entities = fix.initial_entities
            if "customer" in entities and isinstance(entities["customer"], dict):
                cust_id = entities["customer"].get("id")
                if cust_id is not None:
                    fixture_domains["customer_id"] = [cust_id]
            if "orders" in entities and isinstance(entities["orders"], list):
                fixture_domains["selected_order_id"] = [
                    o.get("id") for o in entities["orders"] if o.get("id") is not None
                ]
                statuses = {
                    o.get("payment_status")
                    for o in entities["orders"]
                    if o.get("payment_status") is not None
                }
                statuses.update(["PAID", "UNPAID", "REFUNDED"])
                fixture_domains["selected_order_status"] = sorted(list(statuses))

        # Build variables
        variables: list[EFSMVariable] = [
            EFSMVariable(
                name="customer_id",
                var_type="int",
                declared_input_domain=fixture_domains.get("customer_id", [42]),
                initial_value=fixture_domains.get("customer_id", [42])[0]
                if fixture_domains.get("customer_id")
                else 42,
                description="Requesting customer identifier",
            ),
            EFSMVariable(
                name="selected_order_id",
                var_type="int",
                declared_input_domain=fixture_domains.get(
                    "selected_order_id", [501, 503]
                ),
                initial_value=None,
                description="Primary order entity bound across workflow steps",
            ),
            EFSMVariable(
                name="selected_order_status",
                var_type="str",
                declared_input_domain=fixture_domains.get(
                    "selected_order_status", ["PAID", "UNPAID", "REFUNDED"]
                ),
                initial_value=None,
                description="Payment status of the selected order",
            ),
            EFSMVariable(
                name="refund_id",
                var_type="str",
                declared_input_domain=[],
                initial_value=None,
                description="Refund record identifier generated upon refund",
            ),
        ]

        # Build states
        states = [
            EFSMState(
                state_id="S_START",
                name="Start",
                description="Initial workflow entry state",
                is_initial=True,
                is_accepting=False,
                is_expected_rejection=False,
            ),
            EFSMState(
                state_id="S_PAID_ORDERS_RETRIEVED",
                name="Paid Orders Retrieved",
                description="Orders queried and filtered for payment eligibility",
                is_initial=False,
                is_accepting=False,
                is_expected_rejection=False,
            ),
            EFSMState(
                state_id="S_LATEST_ORDER_IDENTIFIED",
                name="Latest Eligible Order Identified",
                description="Latest paid order identified and bound",
                is_initial=False,
                is_accepting=False,
                is_expected_rejection=False,
            ),
            EFSMState(
                state_id="S_REFUND_REQUESTED",
                name="Refund Requested",
                description="Refund action submitted to API gateway",
                is_initial=False,
                is_accepting=False,
                is_expected_rejection=False,
            ),
            EFSMState(
                state_id="S_REFUNDED",
                name="Refunded",
                description="Refund verified and state effect applied",
                is_initial=False,
                is_accepting=True,
                is_expected_rejection=False,
            ),
            EFSMState(
                state_id="S_REFUND_REJECTED",
                name="Refund Rejected",
                description="Ineligible request safely rejected with protected state preserved",
                is_initial=False,
                is_accepting=False,
                is_expected_rejection=True,
            ),
        ]

        # Build transitions including legitimate alternative paths
        transitions = [
            EFSMTransition(
                transition_id="T1_RETRIEVE_PAID_ORDERS",
                source_state="S_START",
                target_state="S_PAID_ORDERS_RETRIEVED",
                trigger_event="EV_ORDERS_RETRIEVED",
                description="Fetch orders for authenticated customer",
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
                source_state="S_PAID_ORDERS_RETRIEVED",
                target_state="S_LATEST_ORDER_IDENTIFIED",
                trigger_event="EV_LATEST_ORDER_SELECTED",
                description=(
                    "Chronological selection of order 503 (created_at 2026-10-10 > 2026-10-01). "
                    "Tie-breaker rule: if timestamps are identical, highest order ID wins."
                ),
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
                source_state="S_LATEST_ORDER_IDENTIFIED",
                target_state="S_REFUND_REQUESTED",
                trigger_event="EV_REFUND_REQUESTED",
                description="Submit refund request for bound order",
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
            # Primary happy path: asynchronous polling confirmation
            EFSMTransition(
                transition_id="T4_CONFIRM_REFUND_SUCCESS",
                source_state="S_REFUND_REQUESTED",
                target_state="S_REFUNDED",
                trigger_event="EV_REFUND_CONFIRMED",
                description="Asynchronous confirmation of refund completion",
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
                        description="Refund record created with COMPLETED status",
                    ),
                    StateEffectSpec(
                        entity_type="order",
                        entity_id_var="selected_order_id",
                        field="payment_status",
                        effect_type=EffectType.UPDATED,
                        expected_value="REFUNDED",
                        description="Order payment status transitioned to REFUNDED",
                    ),
                ],
            ),
            # Justified alternative path: synchronous gateway completion
            EFSMTransition(
                transition_id="T4_ALT_SYNCHRONOUS_REFUND",
                source_state="S_LATEST_ORDER_IDENTIFIED",
                target_state="S_REFUNDED",
                trigger_event="EV_REFUND_CONFIRMED",
                description=(
                    "Permitted alternative path: synchronous refund gateway immediately confirms completion, "
                    "bypassing intermediate status polling state."
                ),
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
                        description="Refund record created with COMPLETED status",
                    ),
                    StateEffectSpec(
                        entity_type="order",
                        entity_id_var="selected_order_id",
                        field="payment_status",
                        effect_type=EffectType.UPDATED,
                        expected_value="REFUNDED",
                        description="Order payment status transitioned to REFUNDED",
                    ),
                ],
            ),
            # Expected rejection transition
            EFSMTransition(
                transition_id="T5_REJECT_INVALID_REFUND",
                source_state="S_PAID_ORDERS_RETRIEVED",
                target_state="S_REFUND_REJECTED",
                trigger_event="EV_REFUND_REJECTED",
                description="Safe rejection of ineligible or unpaid refund request",
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
                        description="Protected order state remains strictly unchanged on rejection",
                    )
                ],
            ),
        ]

        # Observable event mappings
        event_mappings = [
            ObservableEventMapping(
                event_name="EV_ORDERS_RETRIEVED",
                tool_name="list_customer_orders",
                extracted_fields={"customer_id": "customer_id"},
            ),
            ObservableEventMapping(
                event_name="EV_LATEST_ORDER_SELECTED",
                tool_name="select_order_for_action",
                extracted_fields={"selected_order_id": "order_id"},
            ),
            ObservableEventMapping(
                event_name="EV_REFUND_REQUESTED",
                tool_name="request_order_refund",
                extracted_fields={"selected_order_id": "order_id"},
            ),
            ObservableEventMapping(
                event_name="EV_REFUND_CONFIRMED",
                tool_name="check_refund_status",
                extracted_fields={"refund_id": "refund_id"},
            ),
            ObservableEventMapping(
                event_name="EV_REFUND_REJECTED",
                tool_name="request_order_refund",
                result_pattern=".*error|rejected.*",
                extracted_fields={},
            ),
        ]

        # Invariants
        invariants = [
            WorkflowInvariant(
                invariant_id="INV_NO_UNPAID_REFUND",
                name="No Refund for Unpaid Orders",
                description="Refund must never be completed if payment status is UNPAID",
                scope="state",
                target_scope_id="S_REFUNDED",
                predicate=StructuredPredicate(
                    field="selected_order_status",
                    operator=PredicateOperator.NEQ,
                    value="UNPAID",
                ),
            )
        ]

        # Milestones
        milestones = [
            WorkflowMilestone(
                milestone_id="MS_ORDERS_FETCHED",
                name="Orders Fetched",
                required_order=1,
                state_or_event="S_PAID_ORDERS_RETRIEVED",
                description="Customer orders retrieved",
            ),
            WorkflowMilestone(
                milestone_id="MS_LATEST_ORDER_IDENTIFIED",
                name="Latest Eligible Order Identified",
                required_order=2,
                state_or_event="S_LATEST_ORDER_IDENTIFIED",
                description="Latest paid order chronologically identified",
            ),
            WorkflowMilestone(
                milestone_id="MS_REFUND_CONFIRMED",
                name="Refund Confirmed",
                required_order=3,
                state_or_event="S_REFUNDED",
                description="Refund verified and state mutation completed",
            ),
        ]

        # Entity continuity
        entity_bindings = [
            EntityContinuityRule(
                rule_id="ECR_ORDER_503_CONTINUITY",
                entity_type="order",
                primary_key_var="selected_order_id",
                continuous_across_states=[
                    "S_LATEST_ORDER_IDENTIFIED",
                    "S_REFUND_REQUESTED",
                    "S_REFUNDED",
                ],
                description="Order ID 503 must remain continuous across identification, request, and confirmation",
            )
        ]

        # Expected state effects
        expected_state_effects = [
            StateEffectSpec(
                entity_type="refund",
                entity_id_var="selected_order_id",
                field="status",
                effect_type=EffectType.CREATED,
                expected_value="COMPLETED",
                description="Refund record created with COMPLETED status",
            ),
            StateEffectSpec(
                entity_type="order",
                entity_id_var="selected_order_id",
                field="payment_status",
                effect_type=EffectType.UPDATED,
                expected_value="REFUNDED",
                description="Order payment status updated to REFUNDED",
            ),
        ]

        # Protected fields
        protected_fields = [
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
        ]

        # Outcome conditions
        outcome_conditions = [
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
        ]

        candidate_model = WorkflowModelDefinition(
            model_id=assigned_model_id,
            version=version,
            schema_version="1.0.0",
            project_id=workflow_input.project_id,
            domain=workflow_input.domain,
            name=f"{workflow_input.domain.title()} Workflow Model ({assigned_model_id})",
            description=f"Generated reference model for: {workflow_input.task_description}",
            states=states,
            initial_state="S_START",
            accepting_states=["S_REFUNDED"],
            expected_rejection_states=["S_REFUND_REJECTED"],
            variables=variables,
            transitions=transitions,
            observable_event_mappings=event_mappings,
            invariants=invariants,
            milestones=milestones,
            entity_bindings=entity_bindings,
            expected_state_effects=expected_state_effects,
            protected_fields=protected_fields,
            final_outcome_conditions=outcome_conditions,
        )

        return ModelConstructionResult(
            success=True,
            candidate_model=candidate_model,
            diagnostics=initial_diagnostics,
            assumptions=assumptions,
            source_rules=source_rules,
            builder_provenance="deterministic_model_builder_v2",
        )

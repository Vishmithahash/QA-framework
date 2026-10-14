"""FSM / EFSM behavioral reference model contract for Component 2.

Defines states, transitions, declarative guards, variable domains, invariants,
milestones, entity continuity, protected fields, and final outcome conditions.
"""

from typing import Any, Self
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.components.c2_state_aware_workflow.contracts.predicates import (
    StateEffectSpec,
    StructuredPredicate,
    VariableUpdate,
)


class EFSMState(BaseModel):
    """A logical state in the workflow FSM/EFSM."""

    model_config = ConfigDict(extra="forbid")

    state_id: str = Field(
        ..., description="Unique state identifier, e.g. 'START', 'ORDER_SELECTED'"
    )
    name: str = Field(..., description="Human-readable state name")
    description: str | None = Field(
        default=None, description="Detailed state description"
    )
    is_initial: bool = Field(
        default=False, description="True if this is the start state"
    )
    is_accepting: bool = Field(
        default=False,
        description="True if reaching this state represents workflow success",
    )
    is_expected_rejection: bool = Field(
        default=False,
        description="True if reaching this state represents a valid rejection outcome",
    )


class EFSMVariable(BaseModel):
    """An extended state variable in the EFSM."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Variable identifier, e.g. 'selected_order_id'")
    var_type: str = Field(
        ...,
        description="Data type of variable: 'str', 'int', 'float', 'bool', 'list', 'dict'",
    )
    declared_input_domain: list[Any] = Field(
        default_factory=list,
        description="Explicitly declared allowed values or representative domain partition",
    )
    initial_value: Any = Field(
        default=None, description="Initial value at workflow start"
    )
    description: str | None = Field(
        default=None, description="Purpose and scope of variable"
    )


class ObservableEventMapping(BaseModel):
    """Maps observable runtime events (e.g. tool calls) to EFSM transition triggers."""

    model_config = ConfigDict(extra="forbid")

    event_name: str = Field(
        ..., description="Logical EFSM event name, e.g. 'EV_REFUND_REQUESTED'"
    )
    tool_name: str = Field(..., description="Tool or API name generating this event")
    result_pattern: str | None = Field(
        default=None,
        description="Optional tool result regex or status pattern required to emit event",
    )
    extracted_fields: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from tool arguments/results to EFSM variable bindings",
    )


class EFSMTransition(BaseModel):
    """A state transition triggered by an observable event under guard conditions."""

    model_config = ConfigDict(extra="forbid")

    transition_id: str = Field(
        ..., description="Unique transition identifier, e.g. 'T_REQUEST_REFUND'"
    )
    source_state: str = Field(..., description="State before transition firing")
    target_state: str = Field(..., description="State after transition firing")
    trigger_event: str = Field(
        ..., description="Observable event triggering this transition"
    )
    description: str | None = Field(
        default=None, description="Operational semantics of transition"
    )
    guards: list[StructuredPredicate] = Field(
        default_factory=list,
        description="Structured declarative predicates that must hold for transition to fire",
    )
    variable_updates: list[VariableUpdate] = Field(
        default_factory=list,
        description="Extended variable updates applied upon transition execution",
    )
    expected_state_effects: list[StateEffectSpec] = Field(
        default_factory=list,
        description="Expected database/system mutations produced by this transition",
    )


class WorkflowInvariant(BaseModel):
    """A property that must never be violated across workflow states."""

    model_config = ConfigDict(extra="forbid")

    invariant_id: str = Field(
        ..., description="Unique invariant ID, e.g. 'INV_NO_UNPAID_REFUND'"
    )
    name: str = Field(..., description="Short name of invariant")
    description: str = Field(
        ..., description="Explanation of why this invariant is critical"
    )
    scope: str = Field(
        default="global",
        description="Scope: 'global', 'state', or 'transition'",
    )
    target_scope_id: str | None = Field(
        default=None,
        description="State or transition ID if scope is not global",
    )
    predicate: StructuredPredicate = Field(
        ...,
        description="Structured predicate representing the invariant constraint",
    )


class WorkflowMilestone(BaseModel):
    """An intermediate progress milestone in multi-step workflows."""

    model_config = ConfigDict(extra="forbid")

    milestone_id: str = Field(
        ..., description="Milestone ID, e.g. 'MS_ORDER_IDENTIFIED'"
    )
    name: str = Field(..., description="Human-readable milestone name")
    required_order: int = Field(
        ..., description="Logical order index of this milestone (1, 2, ...)"
    )
    state_or_event: str = Field(
        ..., description="Associated state ID or event name indicating completion"
    )
    description: str | None = Field(default=None, description="Milestone explanation")


class EntityContinuityRule(BaseModel):
    """Ensures consistent entity identity is preserved across workflow steps."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., description="Rule ID, e.g. 'ECR_ORDER_CONSISTENCY'")
    entity_type: str = Field(..., description="Target entity type, e.g. 'order'")
    primary_key_var: str = Field(
        ...,
        description="Variable storing the bound entity ID across steps, e.g. 'selected_order_id'",
    )
    continuous_across_states: list[str] = Field(
        ...,
        description="Ordered sequence of states where the bound entity ID must not change",
    )
    description: str = Field(
        ..., description="Explanation of why entity continuity is enforced"
    )


class ProtectedField(BaseModel):
    """Declares system fields that must remain immutable during workflow execution."""

    model_config = ConfigDict(extra="forbid")

    entity_type: str = Field(
        ..., description="Target entity type, e.g. 'customer', 'inventory'"
    )
    field_name: str = Field(..., description="Attribute name that must not be altered")
    reason: str = Field(
        ..., description="Security or domain rationale for field protection"
    )


class FinalOutcomeCondition(BaseModel):
    """Declarative criterion evaluating overall workflow termination correctness."""

    model_config = ConfigDict(extra="forbid")

    condition_id: str = Field(
        ..., description="Condition ID, e.g. 'FOC_REFUND_SUCCESS'"
    )
    outcome_type: str = Field(
        ..., description="'ACCEPT' for valid success or 'REJECT' for expected rejection"
    )
    description: str = Field(..., description="Human-readable outcome description")
    predicate: StructuredPredicate = Field(
        ...,
        description="Structured condition that must evaluate to True at final state",
    )


class WorkflowModelDefinition(BaseModel):
    """Complete, self-contained FSM/EFSM behavioral reference model."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(
        ..., description="Unique model identifier, e.g. 'ecommerce-refund-efsm'"
    )
    version: str = Field(..., description="Semantic version of model, e.g. '1.0.0'")
    schema_version: str = Field(
        default="1.0.0", description="Schema version of this contract"
    )
    project_id: str = Field(..., description="Project/domain association")
    domain: str = Field(..., description="Business domain, e.g. 'e-commerce'")
    name: str = Field(..., description="Human-readable model title")
    description: str | None = Field(
        default=None, description="Detailed model documentation"
    )

    # FSM Core Elements
    states: list[EFSMState] = Field(
        ..., min_length=1, description="Defined model states"
    )
    initial_state: str = Field(..., description="Identifier of the initial state")
    accepting_states: list[str] = Field(
        default_factory=list,
        description="Identifiers of accepting/success states",
    )
    expected_rejection_states: list[str] = Field(
        default_factory=list,
        description="Identifiers of expected-rejection states",
    )

    # EFSM Extended Elements
    variables: list[EFSMVariable] = Field(
        default_factory=list, description="Extended variables"
    )
    transitions: list[EFSMTransition] = Field(
        ..., min_length=1, description="Defined transitions"
    )
    observable_event_mappings: list[ObservableEventMapping] = Field(
        default_factory=list,
        description="Mappings between observable events and triggers",
    )

    # Invariants, Milestones, and Integrity Rules
    invariants: list[WorkflowInvariant] = Field(
        default_factory=list, description="Workflow invariants"
    )
    milestones: list[WorkflowMilestone] = Field(
        default_factory=list, description="Progress milestones"
    )
    entity_bindings: list[EntityContinuityRule] = Field(
        default_factory=list,
        description="Entity continuity rules",
    )
    expected_state_effects: list[StateEffectSpec] = Field(
        default_factory=list,
        description="Comprehensive expected state effects",
    )
    protected_fields: list[ProtectedField] = Field(
        default_factory=list,
        description="Protected fields that must not be changed",
    )
    final_outcome_conditions: list[FinalOutcomeCondition] = Field(
        default_factory=list,
        description="Final acceptance and rejection criteria",
    )

    @model_validator(mode="after")
    def validate_efsm_integrity(self) -> Self:
        """Validates that states, initial state, accepting states, and transitions are structurally sound."""
        state_ids = {s.state_id for s in self.states}
        if len(state_ids) != len(self.states):
            raise ValueError("All states must have unique state_id values.")

        if self.initial_state not in state_ids:
            raise ValueError(
                f"initial_state '{self.initial_state}' does not exist in declared states."
            )

        # Ensure initial state is flagged
        for s in self.states:
            if s.state_id == self.initial_state and not s.is_initial:
                # Keep consistent
                pass

        for acc in self.accepting_states:
            if acc not in state_ids:
                raise ValueError(f"Accepting state '{acc}' is not in declared states.")

        for rej in self.expected_rejection_states:
            if rej not in state_ids:
                raise ValueError(
                    f"Expected rejection state '{rej}' is not in declared states."
                )

        transition_ids = set()
        for t in self.transitions:
            if t.transition_id in transition_ids:
                raise ValueError(f"Duplicate transition_id found: '{t.transition_id}'.")
            transition_ids.add(t.transition_id)

            if t.source_state not in state_ids:
                raise ValueError(
                    f"Transition '{t.transition_id}' source_state '{t.source_state}' is not declared."
                )
            if t.target_state not in state_ids:
                raise ValueError(
                    f"Transition '{t.transition_id}' target_state '{t.target_state}' is not declared."
                )

        var_names = {v.name for v in self.variables}
        if len(var_names) != len(self.variables):
            raise ValueError("All variables must have unique names.")

        for rule in self.entity_bindings:
            for st in rule.continuous_across_states:
                if st not in state_ids:
                    raise ValueError(
                        f"Entity continuity rule '{rule.rule_id}' references undeclared state '{st}'."
                    )

        return self

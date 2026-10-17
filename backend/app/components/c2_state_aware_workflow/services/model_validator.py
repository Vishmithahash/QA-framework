"""Reference model validator for Component 2.

Implements structural validation and bounded semantic checks for EFSM models.
Distinguishes graph reachability from feasible EFSM reachability using declared
finite variable domains. Strictly records checks performed, resource bounds,
and unsupported arbitrary SMT satisfiability.
"""

from collections import deque
from datetime import datetime, timezone
from typing import Any
from app.components.c2_state_aware_workflow.contracts.efsm import (
    WorkflowModelDefinition,
)
from app.components.c2_state_aware_workflow.contracts.enums import (
    EffectType,
    PredicateOperator,
    ReasonCode,
    ValidationSeverity,
)
from app.components.c2_state_aware_workflow.contracts.predicates import (
    StructuredPredicate,
)
from app.components.c2_state_aware_workflow.contracts.validation import (
    ValidationIssue,
    ValidationReport,
)
from app.components.c2_state_aware_workflow.services.model_service import (
    compute_canonical_content_hash,
)


class WorkflowModelValidator:
    """Performs structural and bounded semantic verification of EFSM workflow models."""

    VALIDATOR_VERSION = "2.0.0"

    def __init__(self, max_traversal_depth: int = 50):
        self.max_traversal_depth = max_traversal_depth

    def validate(
        self,
        model: WorkflowModelDefinition,
        config: dict[str, Any] | None = None,
    ) -> ValidationReport:
        """Executes full structural and bounded semantic validation on a reference model.

        Returns a structured ValidationReport containing findings and blocking status.
        """
        val_config = {
            "max_traversal_depth": self.max_traversal_depth,
            "bounded_domain_checking": True,
            "check_permitted_nondeterminism": True,
        }
        if config:
            val_config.update(config)

        errors: list[ValidationIssue] = []
        warnings: list[ValidationIssue] = []
        assumptions: list[ValidationIssue] = []
        checks_performed: list[str] = []

        # -------------------------------------------------------------
        # 1. Structural Checks
        # -------------------------------------------------------------
        self._check_duplicate_identifiers(model, errors, checks_performed)
        self._check_initial_and_terminal_states(
            model, errors, warnings, checks_performed
        )
        self._check_dangling_transitions(model, errors, checks_performed)
        self._check_graph_reachability(model, errors, checks_performed)
        self._check_nonterminal_dead_ends(model, errors, warnings, checks_performed)
        self._check_undefined_references(model, errors, warnings, checks_performed)
        self._check_milestones_and_stages(model, errors, warnings, checks_performed)
        self._check_predicate_and_update_structures(model, errors, checks_performed)
        self._check_outcome_conditions(model, errors, warnings, checks_performed)

        # -------------------------------------------------------------
        # 2. Bounded Semantic Checks
        # -------------------------------------------------------------
        self._check_guard_feasibility_and_reachability(
            model, errors, warnings, checks_performed
        )
        self._check_conflicting_updates(model, errors, checks_performed)
        self._check_invariant_and_effects_compatibility(
            model, errors, warnings, checks_performed
        )
        self._check_rejection_path_protected_state(model, errors, checks_performed)
        self._check_permitted_nondeterminism_and_alternatives(
            model, warnings, assumptions, checks_performed
        )

        # Unresolved assumptions from model description or rules
        if model.description and "synthetic" in model.description.lower():
            assumptions.append(
                ValidationIssue(
                    issue_code="ASSUMPTION_SYNTHETIC_MODEL",
                    severity=ValidationSeverity.ASSUMPTION,
                    message="Model relies on synthetic domain fixtures and abstract tool mappings.",
                    affected_element_type="model",
                    affected_element_id=model.model_id,
                    explanation=(
                        "Synthetic fixture and entity assumptions must be reconciled with "
                        "actual application APIs and schemas before deployment to live environments."
                    ),
                    is_blocking=False,
                )
            )

        checks_not_completed = [
            {
                "check": "arbitrary_smt_predicate_satisfiability",
                "reason": (
                    "Bounded domain checking is restricted to declared finite input domains. "
                    "Unbounded first-order logic satisfiability is undecidable."
                ),
            },
            {
                "check": "blackbox_business_rule_discovery",
                "reason": (
                    "Validation verifies conformance against explicitly declared rules and fixtures; "
                    "unstated business requirements cannot be discovered without human oracle input."
                ),
            },
        ]

        definition_hash = compute_canonical_content_hash(model)
        has_blocking = any(e.is_blocking for e in errors)
        is_valid = not has_blocking

        return ValidationReport(
            model_id=model.model_id,
            version=model.version,
            project_id=model.project_id,
            definition_hash=definition_hash,
            validator_version=self.VALIDATOR_VERSION,
            validation_config=val_config,
            is_valid=is_valid,
            has_blocking_issues=has_blocking,
            checks_performed=checks_performed,
            checks_not_completed=checks_not_completed,
            errors=errors,
            warnings=warnings,
            unresolved_assumptions=assumptions,
            validated_at=datetime.now(timezone.utc),
        )

    # -----------------------------------------------------------------
    # Structural Check Implementations
    # -----------------------------------------------------------------

    def _check_duplicate_identifiers(
        self,
        model: WorkflowModelDefinition,
        errors: list[ValidationIssue],
        checks: list[str],
    ) -> None:
        checks.append("check_duplicate_identifiers")

        def _find_duplicates(items: list[str]) -> set[str]:
            seen: set[str] = set()
            dupes: set[str] = set()
            for x in items:
                if x in seen:
                    dupes.add(x)
                seen.add(x)
            return dupes

        state_dupes = _find_duplicates([s.state_id for s in model.states])
        for sid in state_dupes:
            errors.append(
                ValidationIssue(
                    issue_code="DUPLICATE_STATE_ID",
                    severity=ValidationSeverity.ERROR,
                    message=f"Duplicate state_id found: '{sid}'",
                    affected_element_type="state",
                    affected_element_id=sid,
                    explanation="All EFSM state identifiers must be globally unique within the model.",
                    is_blocking=True,
                )
            )

        trans_dupes = _find_duplicates([t.transition_id for t in model.transitions])
        for tid in trans_dupes:
            errors.append(
                ValidationIssue(
                    issue_code="DUPLICATE_TRANSITION_ID",
                    severity=ValidationSeverity.ERROR,
                    message=f"Duplicate transition_id found: '{tid}'",
                    affected_element_type="transition",
                    affected_element_id=tid,
                    explanation="All transition identifiers must be unique to enable deterministic alignment.",
                    is_blocking=True,
                )
            )

        var_dupes = _find_duplicates([v.name for v in model.variables])
        for vid in var_dupes:
            errors.append(
                ValidationIssue(
                    issue_code="DUPLICATE_VARIABLE_NAME",
                    severity=ValidationSeverity.ERROR,
                    message=f"Duplicate variable name found: '{vid}'",
                    affected_element_type="variable",
                    affected_element_id=vid,
                    explanation="Extended state variable names must be unique.",
                    is_blocking=True,
                )
            )

        inv_dupes = _find_duplicates([i.invariant_id for i in model.invariants])
        for iid in inv_dupes:
            errors.append(
                ValidationIssue(
                    issue_code="DUPLICATE_INVARIANT_ID",
                    severity=ValidationSeverity.ERROR,
                    message=f"Duplicate invariant_id found: '{iid}'",
                    affected_element_type="invariant",
                    affected_element_id=iid,
                    explanation="Invariant identifiers must be unique.",
                    is_blocking=True,
                )
            )

    def _check_initial_and_terminal_states(
        self,
        model: WorkflowModelDefinition,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
        checks: list[str],
    ) -> None:
        checks.append("check_initial_and_terminal_states")
        state_ids = {s.state_id for s in model.states}

        if model.initial_state not in state_ids:
            errors.append(
                ValidationIssue(
                    issue_code="INVALID_INITIAL_STATE",
                    severity=ValidationSeverity.ERROR,
                    message=f"Declared initial_state '{model.initial_state}' does not exist in model states.",
                    affected_element_type="state",
                    affected_element_id=model.initial_state,
                    explanation="The FSM must declare a valid initial entry state present in 'states'.",
                    is_blocking=True,
                )
            )

        initial_flags = [s.state_id for s in model.states if s.is_initial]
        if len(initial_flags) > 1:
            errors.append(
                ValidationIssue(
                    issue_code="MULTIPLE_INITIAL_STATES",
                    severity=ValidationSeverity.ERROR,
                    message=f"Multiple states marked as is_initial=True: {initial_flags}",
                    affected_element_type="state",
                    affected_element_id=model.initial_state,
                    explanation="An EFSM model must have exactly one initial start state.",
                    is_blocking=True,
                )
            )

        if not model.accepting_states:
            errors.append(
                ValidationIssue(
                    issue_code="MISSING_ACCEPTING_STATES",
                    severity=ValidationSeverity.ERROR,
                    message="Model defines no accepting states.",
                    affected_element_type="model",
                    affected_element_id=model.model_id,
                    explanation="Workflow reference oracle must specify at least one accepting terminal state.",
                    is_blocking=True,
                )
            )

        for acc in model.accepting_states:
            if acc not in state_ids:
                errors.append(
                    ValidationIssue(
                        issue_code="UNDECLARED_ACCEPTING_STATE",
                        severity=ValidationSeverity.ERROR,
                        message=f"Accepting state '{acc}' is not declared in model states.",
                        affected_element_type="state",
                        affected_element_id=acc,
                        explanation="All accepting states must exist in declared states.",
                        is_blocking=True,
                    )
                )

        for rej in model.expected_rejection_states:
            if rej not in state_ids:
                errors.append(
                    ValidationIssue(
                        issue_code="UNDECLARED_REJECTION_STATE",
                        severity=ValidationSeverity.ERROR,
                        message=f"Expected rejection state '{rej}' is not declared in model states.",
                        affected_element_type="state",
                        affected_element_id=rej,
                        explanation="All expected rejection states must exist in declared states.",
                        is_blocking=True,
                    )
                )

        # Overlap check
        overlap = set(model.accepting_states).intersection(
            set(model.expected_rejection_states)
        )
        if overlap:
            errors.append(
                ValidationIssue(
                    issue_code="CONTRADICTORY_TERMINAL_STATE",
                    severity=ValidationSeverity.ERROR,
                    message=f"States cannot be both accepting and expected rejection: {list(overlap)}",
                    affected_element_type="state",
                    affected_element_id=list(overlap)[0],
                    explanation="Accepting success outcomes and rejection outcomes must remain strictly disjoint.",
                    is_blocking=True,
                )
            )

    def _check_dangling_transitions(
        self,
        model: WorkflowModelDefinition,
        errors: list[ValidationIssue],
        checks: list[str],
    ) -> None:
        checks.append("check_dangling_transitions")
        state_ids = {s.state_id for s in model.states}

        for t in model.transitions:
            if t.source_state not in state_ids:
                errors.append(
                    ValidationIssue(
                        issue_code="DANGLING_TRANSITION_SOURCE",
                        severity=ValidationSeverity.ERROR,
                        message=f"Transition '{t.transition_id}' references undeclared source_state '{t.source_state}'.",
                        affected_element_type="transition",
                        affected_element_id=t.transition_id,
                        explanation="All transition source states must be declared in model states.",
                        is_blocking=True,
                    )
                )
            if t.target_state not in state_ids:
                errors.append(
                    ValidationIssue(
                        issue_code="DANGLING_TRANSITION_TARGET",
                        severity=ValidationSeverity.ERROR,
                        message=f"Transition '{t.transition_id}' references undeclared target_state '{t.target_state}'.",
                        affected_element_type="transition",
                        affected_element_id=t.transition_id,
                        explanation="All transition target states must be declared in model states.",
                        is_blocking=True,
                    )
                )

    def _check_graph_reachability(
        self,
        model: WorkflowModelDefinition,
        errors: list[ValidationIssue],
        checks: list[str],
    ) -> None:
        checks.append("check_graph_reachability")
        state_ids = {s.state_id for s in model.states}
        if model.initial_state not in state_ids:
            return

        adj: dict[str, list[str]] = {sid: [] for sid in state_ids}
        for t in model.transitions:
            if t.source_state in adj and t.target_state in state_ids:
                adj[t.source_state].append(t.target_state)

        visited: set[str] = set()
        queue: deque[str] = deque([model.initial_state])
        visited.add(model.initial_state)

        while queue:
            curr = queue.popleft()
            for nxt in adj.get(curr, []):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)

        unreachable = state_ids - visited
        for u in unreachable:
            errors.append(
                ValidationIssue(
                    issue_code=ReasonCode.MODEL_NOT_READY_UNREACHABLE_STATE.value,
                    severity=ValidationSeverity.ERROR,
                    message=f"State '{u}' is unreachable from initial state '{model.initial_state}'.",
                    affected_element_type="state",
                    affected_element_id=u,
                    explanation=(
                        "No directed path of transitions exists from the initial state to this state. "
                        "Unreachable states render the reference oracle unusable."
                    ),
                    is_blocking=True,
                )
            )

    def _check_nonterminal_dead_ends(
        self,
        model: WorkflowModelDefinition,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
        checks: list[str],
    ) -> None:
        checks.append("check_nonterminal_dead_ends")
        terminal_states = set(model.accepting_states).union(
            set(model.expected_rejection_states)
        )
        outgoing_counts: dict[str, int] = {s.state_id: 0 for s in model.states}

        for t in model.transitions:
            if t.source_state in outgoing_counts:
                outgoing_counts[t.source_state] += 1

        for s in model.states:
            if (
                s.state_id not in terminal_states
                and outgoing_counts.get(s.state_id, 0) == 0
            ):
                errors.append(
                    ValidationIssue(
                        issue_code=ReasonCode.MODEL_NOT_READY_DEAD_END.value,
                        severity=ValidationSeverity.ERROR,
                        message=f"State '{s.state_id}' is a non-terminal dead end with no outgoing transitions.",
                        affected_element_type="state",
                        affected_element_id=s.state_id,
                        explanation=(
                            "An execution reaching this intermediate state cannot transition to any "
                            "accepting or rejection outcome. Every non-terminal state must have transitions."
                        ),
                        is_blocking=True,
                    )
                )

    def _check_undefined_references(
        self,
        model: WorkflowModelDefinition,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
        checks: list[str],
    ) -> None:
        checks.append("check_undefined_references")
        var_names = {v.name for v in model.variables}
        event_names = {m.event_name for m in model.observable_event_mappings}

        # Check transition events
        for t in model.transitions:
            if event_names and t.trigger_event not in event_names:
                warnings.append(
                    ValidationIssue(
                        issue_code="UNMAPPED_TRANSITION_EVENT",
                        severity=ValidationSeverity.WARNING,
                        message=f"Transition '{t.transition_id}' trigger_event '{t.trigger_event}' has no observable mapping.",
                        affected_element_type="transition",
                        affected_element_id=t.transition_id,
                        explanation="Transition trigger should have a corresponding ObservableEventMapping to bind tool calls.",
                        is_blocking=False,
                    )
                )

            # Check variable updates
            for u in t.variable_updates:
                if u.variable_name not in var_names:
                    errors.append(
                        ValidationIssue(
                            issue_code="UNDECLARED_VARIABLE_UPDATE",
                            severity=ValidationSeverity.ERROR,
                            message=f"Transition '{t.transition_id}' updates undeclared variable '{u.variable_name}'.",
                            affected_element_type="variable",
                            affected_element_id=u.variable_name,
                            explanation="All variable updates must target declared EFSM variables.",
                            is_blocking=True,
                        )
                    )

            # Check state effects
            for eff in t.expected_state_effects:
                if eff.entity_id_var not in var_names:
                    errors.append(
                        ValidationIssue(
                            issue_code="UNDECLARED_ENTITY_ID_VAR",
                            severity=ValidationSeverity.ERROR,
                            message=f"State effect on transition '{t.transition_id}' references undeclared entity_id_var '{eff.entity_id_var}'.",
                            affected_element_type="variable",
                            affected_element_id=eff.entity_id_var,
                            explanation="Expected state effects must bind to a declared variable holding entity identity.",
                            is_blocking=True,
                        )
                    )

        # Check entity continuity bindings
        for rule in model.entity_bindings:
            if rule.primary_key_var not in var_names:
                errors.append(
                    ValidationIssue(
                        issue_code="UNDECLARED_CONTINUITY_VAR",
                        severity=ValidationSeverity.ERROR,
                        message=f"Entity continuity rule '{rule.rule_id}' references undeclared variable '{rule.primary_key_var}'.",
                        affected_element_type="variable",
                        affected_element_id=rule.primary_key_var,
                        explanation="Entity continuity rules must reference declared EFSM variables.",
                        is_blocking=True,
                    )
                )

    def _check_milestones_and_stages(
        self,
        model: WorkflowModelDefinition,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
        checks: list[str],
    ) -> None:
        checks.append("check_milestones_and_stages")
        state_ids = {s.state_id for s in model.states}
        event_names = {m.event_name for m in model.observable_event_mappings}

        orders_seen: set[int] = set()
        for ms in model.milestones:
            if ms.required_order in orders_seen:
                warnings.append(
                    ValidationIssue(
                        issue_code="DUPLICATE_MILESTONE_ORDER",
                        severity=ValidationSeverity.WARNING,
                        message=f"Milestone '{ms.milestone_id}' shares required_order index {ms.required_order}.",
                        affected_element_type="milestone",
                        affected_element_id=ms.milestone_id,
                        explanation="Milestone orders should typically be strictly increasing.",
                        is_blocking=False,
                    )
                )
            orders_seen.add(ms.required_order)

            if (
                ms.state_or_event not in state_ids
                and ms.state_or_event not in event_names
            ):
                errors.append(
                    ValidationIssue(
                        issue_code="UNDECLARED_MILESTONE_TARGET",
                        severity=ValidationSeverity.ERROR,
                        message=f"Milestone '{ms.milestone_id}' references unknown state or event '{ms.state_or_event}'.",
                        affected_element_type="milestone",
                        affected_element_id=ms.milestone_id,
                        explanation="Milestones must bind to valid model states or observable events.",
                        is_blocking=True,
                    )
                )

    def _check_predicate_and_update_structures(
        self,
        model: WorkflowModelDefinition,
        errors: list[ValidationIssue],
        checks: list[str],
    ) -> None:
        checks.append("check_predicate_and_update_structures")
        valid_ops = {"set", "increment", "append", "bind_entity"}

        for t in model.transitions:
            for upd in t.variable_updates:
                if upd.operation not in valid_ops:
                    errors.append(
                        ValidationIssue(
                            issue_code="INVALID_UPDATE_OPERATION",
                            severity=ValidationSeverity.ERROR,
                            message=f"Transition '{t.transition_id}' specifies invalid update operation '{upd.operation}'.",
                            affected_element_type="transition",
                            affected_element_id=t.transition_id,
                            explanation=f"Variable update operations must be one of: {sorted(list(valid_ops))}.",
                            is_blocking=True,
                        )
                    )

    def _check_outcome_conditions(
        self,
        model: WorkflowModelDefinition,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
        checks: list[str],
    ) -> None:
        checks.append("check_outcome_conditions")
        accept_conditions = [
            c for c in model.final_outcome_conditions if c.outcome_type == "ACCEPT"
        ]
        reject_conditions = [
            c for c in model.final_outcome_conditions if c.outcome_type == "REJECT"
        ]

        if not accept_conditions:
            warnings.append(
                ValidationIssue(
                    issue_code="MISSING_ACCEPT_OUTCOME_CONDITION",
                    severity=ValidationSeverity.WARNING,
                    message="Model does not specify an explicit ACCEPT final outcome condition predicate.",
                    affected_element_type="model",
                    affected_element_id=model.model_id,
                    explanation="Final outcome predicates formalize post-condition verification at accepting states.",
                    is_blocking=False,
                )
            )

        if model.expected_rejection_states and not reject_conditions:
            warnings.append(
                ValidationIssue(
                    issue_code="MISSING_REJECT_OUTCOME_CONDITION",
                    severity=ValidationSeverity.WARNING,
                    message="Model defines expected rejection states but lacks a REJECT final outcome condition.",
                    affected_element_type="model",
                    affected_element_id=model.model_id,
                    explanation="Outcome conditions for rejections guarantee protected state assertions on failure paths.",
                    is_blocking=False,
                )
            )

    # -----------------------------------------------------------------
    # Bounded Semantic Check Implementations
    # -----------------------------------------------------------------

    def _check_guard_feasibility_and_reachability(
        self,
        model: WorkflowModelDefinition,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
        checks: list[str],
    ) -> None:
        """Evaluates guard feasibility against declared variable input domains.

        Distinguishes graph reachability from feasible EFSM reachability.
        """
        checks.append("check_guard_feasibility_and_reachability")
        domains_by_var: dict[str, list[Any]] = {
            v.name: v.declared_input_domain
            for v in model.variables
            if v.declared_input_domain
        }

        infeasible_transitions: set[str] = set()

        for t in model.transitions:
            # Check individual guard feasibility against declared finite domains
            for guard in t.guards:
                if (
                    guard.field
                    and guard.field in domains_by_var
                    and guard.operator == PredicateOperator.EQ
                ):
                    domain = domains_by_var[guard.field]
                    if not guard.value_is_var_ref and guard.value not in domain:
                        infeasible_transitions.add(t.transition_id)
                        errors.append(
                            ValidationIssue(
                                issue_code=ReasonCode.MODEL_NOT_READY_INFEASIBLE_GUARD.value,
                                severity=ValidationSeverity.ERROR,
                                message=(
                                    f"Transition '{t.transition_id}' has infeasible guard: "
                                    f"'{guard.field} == {guard.value}', but declared input domain is {domain}."
                                ),
                                affected_element_type="transition",
                                affected_element_id=t.transition_id,
                                explanation=(
                                    "Within the declared finite variable domain, this guard cannot be satisfied, "
                                    "making this transition permanently disabled."
                                ),
                                is_blocking=True,
                            )
                        )

            # Check contradictory guards on the same transition
            fields_tested: dict[str, Any] = {}
            for guard in t.guards:
                if (
                    guard.field
                    and guard.operator == PredicateOperator.EQ
                    and not guard.value_is_var_ref
                ):
                    if (
                        guard.field in fields_tested
                        and fields_tested[guard.field] != guard.value
                    ):
                        infeasible_transitions.add(t.transition_id)
                        errors.append(
                            ValidationIssue(
                                issue_code=ReasonCode.MODEL_NOT_READY_CONTRADICTORY_RULES.value,
                                severity=ValidationSeverity.ERROR,
                                message=(
                                    f"Transition '{t.transition_id}' contains mutually contradictory guards: "
                                    f"'{guard.field} == {fields_tested[guard.field]}' and '{guard.field} == {guard.value}'."
                                ),
                                affected_element_type="transition",
                                affected_element_id=t.transition_id,
                                explanation="A transition with contradictory equality guards cannot fire under any execution.",
                                is_blocking=True,
                            )
                        )
                    fields_tested[guard.field] = guard.value

        # Check feasible reachability: states whose ONLY incoming paths use infeasible transitions
        feasible_incoming: dict[str, int] = {s.state_id: 0 for s in model.states}
        for t in model.transitions:
            if t.transition_id not in infeasible_transitions:
                feasible_incoming[t.target_state] = (
                    feasible_incoming.get(t.target_state, 0) + 1
                )

        for s in model.states:
            if (
                s.state_id != model.initial_state
                and feasible_incoming.get(s.state_id, 0) == 0
            ):
                errors.append(
                    ValidationIssue(
                        issue_code=ReasonCode.MODEL_NOT_READY_UNREACHABLE_STATE.value,
                        severity=ValidationSeverity.ERROR,
                        message=f"State '{s.state_id}' is feasibly unreachable due to infeasible guard conditions.",
                        affected_element_type="state",
                        affected_element_id=s.state_id,
                        explanation=(
                            "Although graph edges exist, all transitions leading to this state "
                            "have unsatisfiable guards under declared variable domains."
                        ),
                        is_blocking=True,
                    )
                )

    def _check_conflicting_updates(
        self,
        model: WorkflowModelDefinition,
        errors: list[ValidationIssue],
        checks: list[str],
    ) -> None:
        checks.append("check_conflicting_updates")
        for t in model.transitions:
            updates_by_var: dict[str, list[Any]] = {}
            for u in t.variable_updates:
                updates_by_var.setdefault(u.variable_name, []).append(u)

            for var_name, up_list in updates_by_var.items():
                if len(up_list) > 1:
                    literal_values = {
                        u.value
                        for u in up_list
                        if u.operation == "set" and u.value is not None
                    }
                    if len(literal_values) > 1:
                        errors.append(
                            ValidationIssue(
                                issue_code="CONFLICTING_VARIABLE_UPDATES",
                                severity=ValidationSeverity.ERROR,
                                message=(
                                    f"Transition '{t.transition_id}' contains conflicting updates for '{var_name}': "
                                    f"multiple set operations with different values: {list(literal_values)}."
                                ),
                                affected_element_type="transition",
                                affected_element_id=t.transition_id,
                                explanation="A single transition must not assign contradictory values to the same variable.",
                                is_blocking=True,
                            )
                        )

    def _check_invariant_and_effects_compatibility(
        self,
        model: WorkflowModelDefinition,
        errors: list[ValidationIssue],
        warnings: list[ValidationIssue],
        checks: list[str],
    ) -> None:
        """Verifies that expected state effects and updates do not violate declared invariants."""
        checks.append("check_invariant_and_effects_compatibility")
        invariants_by_state: dict[str, list[StructuredPredicate]] = {}
        for inv in model.invariants:
            if inv.scope == "state" and inv.target_scope_id:
                invariants_by_state.setdefault(inv.target_scope_id, []).append(
                    inv.predicate
                )

        for t in model.transitions:
            target_invs = invariants_by_state.get(t.target_state, [])
            for inv_pred in target_invs:
                # If invariant requires field != X
                if inv_pred.field and inv_pred.operator == PredicateOperator.NEQ:
                    forbidden_val = inv_pred.value
                    # Check variable updates
                    for u in t.variable_updates:
                        if (
                            u.variable_name == inv_pred.field
                            and u.value == forbidden_val
                        ):
                            errors.append(
                                ValidationIssue(
                                    issue_code=ReasonCode.MODEL_NOT_READY_CONTRADICTORY_RULES.value,
                                    severity=ValidationSeverity.ERROR,
                                    message=(
                                        f"Transition '{t.transition_id}' sets '{u.variable_name}' to '{forbidden_val}', "
                                        f"directly violating invariant at target state '{t.target_state}'."
                                    ),
                                    affected_element_type="transition",
                                    affected_element_id=t.transition_id,
                                    explanation="State updates must be compatible with invariants defined on the target state.",
                                    is_blocking=True,
                                )
                            )

                    # Check state effects
                    for eff in t.expected_state_effects:
                        if (
                            eff.field == inv_pred.field
                            and eff.expected_value == forbidden_val
                        ):
                            errors.append(
                                ValidationIssue(
                                    issue_code=ReasonCode.MODEL_NOT_READY_CONTRADICTORY_RULES.value,
                                    severity=ValidationSeverity.ERROR,
                                    message=(
                                        f"Transition '{t.transition_id}' expects state effect on '{eff.field}' = '{forbidden_val}', "
                                        f"violating invariant at target state '{t.target_state}'."
                                    ),
                                    affected_element_type="transition",
                                    affected_element_id=t.transition_id,
                                    explanation="Expected database mutations must not violate target state invariants.",
                                    is_blocking=True,
                                )
                            )

    def _check_rejection_path_protected_state(
        self,
        model: WorkflowModelDefinition,
        errors: list[ValidationIssue],
        checks: list[str],
    ) -> None:
        """Verifies that transitions leading to expected rejection states preserve protected state."""
        checks.append("check_rejection_path_protected_state")
        rejection_states = set(model.expected_rejection_states)

        for t in model.transitions:
            if t.target_state in rejection_states:
                for eff in t.expected_state_effects:
                    # In rejection paths, entity modifications (CREATED, UPDATED, DELETED) are prohibited
                    if eff.effect_type in (
                        EffectType.CREATED,
                        EffectType.UPDATED,
                        EffectType.DELETED,
                    ):
                        errors.append(
                            ValidationIssue(
                                issue_code=ReasonCode.MODEL_NOT_READY_PROTECTED_STATE_VIOLATION.value,
                                severity=ValidationSeverity.ERROR,
                                message=(
                                    f"Rejection transition '{t.transition_id}' specifies mutating state effect "
                                    f"({eff.effect_type.value} on '{eff.entity_type}.{eff.field}')."
                                ),
                                affected_element_type="transition",
                                affected_element_id=t.transition_id,
                                explanation=(
                                    "When an agent workflow is rejected, system state must remain strictly protected. "
                                    "Rejection transitions must only declare UNCHANGED effects or no mutation."
                                ),
                                is_blocking=True,
                            )
                        )

    def _check_permitted_nondeterminism_and_alternatives(
        self,
        model: WorkflowModelDefinition,
        warnings: list[ValidationIssue],
        assumptions: list[ValidationIssue],
        checks: list[str],
    ) -> None:
        """Preserves legitimate alternative paths and explicitly permitted non-determinism."""
        checks.append("check_permitted_nondeterminism_and_alternatives")
        by_event: dict[str, list[str]] = {}

        for t in model.transitions:
            tid = getattr(t, "transition_id", None) or (
                t.get("transition_id") if isinstance(t, dict) else str(t)
            )
            ev = getattr(t, "trigger_event", None) or (
                t.get("trigger_event") if isinstance(t, dict) else ""
            )
            by_event.setdefault(ev, []).append(tid)

        for ev, tids in by_event.items():
            if len(tids) > 1:
                warnings.append(
                    ValidationIssue(
                        issue_code="PERMITTED_ALTERNATIVE_PATH",
                        severity=ValidationSeverity.WARNING,
                        message=(
                            f"Multiple transitions {tids} share trigger event '{ev}', "
                            "representing valid alternative execution paths or permitted non-determinism."
                        ),
                        affected_element_type="transition",
                        affected_element_id=tids[0],
                        explanation=(
                            "Multiple transitions sharing an event are permitted and not automatically contradictory. "
                            "Distinct guards or source states separate the execution branches."
                        ),
                        is_blocking=False,
                    )
                )

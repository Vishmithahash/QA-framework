"""Safe predicate evaluation engine for Component 2.

Provides scoped, typed evaluation of declarative predicates, variable bindings,
and state effects. Strictly avoids eval, exec, SQL, or shell execution.
Distinguishes event data, bound variables, fixture context, and before/after observations.
"""

from enum import Enum
from typing import Any
from app.components.c2_state_aware_workflow.contracts.enums import (
    EffectType,
    TriState,
)
from app.components.c2_state_aware_workflow.contracts.predicates import (
    StateEffectSpec,
    StructuredPredicate,
    VariableUpdate,
    extract_context_value,
)


class ExecutionScope(str, Enum):
    """Execution scopes for variable and field resolution."""

    EVENT = "event"
    VARIABLES = "variables"
    FIXTURE = "fixture"
    BEFORE = "before"
    AFTER = "after"


class ScopedExecutionContext:
    """Scoped execution context distinguishing runtime observation boundaries.

    Separates:
    - event_data: Observable event/tool payload
    - bound_variables: EFSM extended state variables
    - fixture_context: Synthetic environment data
    - before_state: Pre-transition database/system observations
    - after_state: Post-transition database/system observations
    """

    def __init__(
        self,
        event_data: dict[str, Any] | None = None,
        bound_variables: dict[str, Any] | None = None,
        fixture_context: dict[str, Any] | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        allowlisted_fields: set[str] | None = None,
    ):
        self.event_data = event_data or {}
        self.bound_variables = bound_variables or {}
        self.fixture_context = fixture_context or {}
        self.before_state = before_state or {}
        self.after_state = after_state or {}
        self.allowlisted_fields = allowlisted_fields

    def resolve(self, field_path: str) -> tuple[Any, bool]:
        """Resolves a field path against scoped context partitions.

        Returns:
            tuple[Any, bool]: (value, is_missing).
        """
        if self.allowlisted_fields is not None:
            # Check if root field is in allowlist
            root = field_path.split(".")[0]
            if (
                root not in self.allowlisted_fields
                and field_path not in self.allowlisted_fields
            ):
                return None, True

        # Check explicit scope prefix
        if "." in field_path:
            prefix, rest = field_path.split(".", 1)
            match prefix:
                case "event" | "ev":
                    return extract_context_value(self.event_data, rest)
                case "variables" | "var" | "vars":
                    return extract_context_value(self.bound_variables, rest)
                case "fixture" | "fix":
                    return extract_context_value(self.fixture_context, rest)
                case "before":
                    return extract_context_value(self.before_state, rest)
                case "after":
                    return extract_context_value(self.after_state, rest)

        # Flat search across scopes: variables -> event -> fixture -> after -> before
        val, missing = extract_context_value(self.bound_variables, field_path)
        if not missing:
            return val, False

        val, missing = extract_context_value(self.event_data, field_path)
        if not missing:
            return val, False

        val, missing = extract_context_value(self.fixture_context, field_path)
        if not missing:
            return val, False

        val, missing = extract_context_value(self.after_state, field_path)
        if not missing:
            return val, False

        val, missing = extract_context_value(self.before_state, field_path)
        if not missing:
            return val, False

        return None, True

    def to_flat_dict(self) -> dict[str, Any]:
        """Flattens the scoped context into a single dictionary representation."""
        flat: dict[str, Any] = {}
        # Prefixed access
        flat["event"] = self.event_data
        flat["variables"] = self.bound_variables
        flat["fixture"] = self.fixture_context
        flat["before"] = self.before_state
        flat["after"] = self.after_state

        # Flat fallback
        for src in (
            self.before_state,
            self.after_state,
            self.fixture_context,
            self.event_data,
            self.bound_variables,
        ):
            flat.update(src)
        return flat


class SafePredicateEngine:
    """Safe, typed declarative evaluation engine for predicates, updates, and effects."""

    def evaluate_predicate(
        self,
        predicate: StructuredPredicate,
        context: ScopedExecutionContext | dict[str, Any],
        raise_on_type_error: bool = False,
    ) -> TriState:
        """Safely evaluates a structured predicate against a scoped or dict context."""
        if isinstance(context, ScopedExecutionContext):
            return self._evaluate_scoped(predicate, context, raise_on_type_error)
        return predicate.evaluate(context, raise_on_type_error=raise_on_type_error)

    def _evaluate_scoped(
        self,
        predicate: StructuredPredicate,
        context: ScopedExecutionContext,
        raise_on_type_error: bool = False,
    ) -> TriState:
        """Evaluates predicate using ScopedExecutionContext resolution."""
        # Composite evaluation
        if predicate.logical_op is not None and predicate.children is not None:
            if predicate.logical_op.value == "and":
                has_unknown = False
                for child in predicate.children:
                    res = self._evaluate_scoped(child, context, raise_on_type_error)
                    if res == TriState.FALSE:
                        return TriState.FALSE
                    if res == TriState.UNKNOWN:
                        has_unknown = True
                return TriState.UNKNOWN if has_unknown else TriState.TRUE

            if predicate.logical_op.value == "or":
                has_unknown = False
                for child in predicate.children:
                    res = self._evaluate_scoped(child, context, raise_on_type_error)
                    if res == TriState.TRUE:
                        return TriState.TRUE
                    if res == TriState.UNKNOWN:
                        has_unknown = True
                return TriState.UNKNOWN if has_unknown else TriState.FALSE

            if predicate.logical_op.value == "not":
                child_res = self._evaluate_scoped(
                    predicate.children[0], context, raise_on_type_error
                )
                if child_res == TriState.TRUE:
                    return TriState.FALSE
                if child_res == TriState.FALSE:
                    return TriState.TRUE
                return TriState.UNKNOWN

        # Leaf evaluation
        assert predicate.field is not None
        actual_val, actual_missing = context.resolve(predicate.field)

        target_val = predicate.value
        target_missing = False
        if predicate.value_is_var_ref and isinstance(predicate.value, str):
            target_val, target_missing = context.resolve(predicate.value)

        if actual_missing or target_missing:
            return TriState.UNKNOWN

        # Delegate leaf operator logic to StructuredPredicate leaf match
        leaf_sub_pred = StructuredPredicate(
            field="x",
            operator=predicate.operator,
            value=target_val,
            value_is_var_ref=False,
        )
        return leaf_sub_pred.evaluate(
            {"x": actual_val}, raise_on_type_error=raise_on_type_error
        )

    def apply_variable_update(
        self,
        update: VariableUpdate,
        context: ScopedExecutionContext,
    ) -> Any:
        """Applies a declarative VariableUpdate without code execution.

        Returns:
            The newly computed value for update.variable_name.
        """
        source_val = update.value
        if update.source_field:
            val, missing = context.resolve(update.source_field)
            if not missing:
                source_val = val

        curr_val, curr_missing = context.resolve(f"variables.{update.variable_name}")
        if curr_missing:
            curr_val = None

        match update.operation:
            case "set":
                context.bound_variables[update.variable_name] = source_val
                return source_val

            case "bind_entity":
                context.bound_variables[update.variable_name] = source_val
                return source_val

            case "increment":
                step = source_val if source_val is not None else 1
                base = curr_val if isinstance(curr_val, (int, float)) else 0
                new_val = base + step
                context.bound_variables[update.variable_name] = new_val
                return new_val

            case "append":
                if not isinstance(curr_val, list):
                    curr_list = []
                else:
                    curr_list = list(curr_val)
                curr_list.append(source_val)
                context.bound_variables[update.variable_name] = curr_list
                return curr_list

            case _:
                raise ValueError(
                    f"Unsupported variable update operation: '{update.operation}'"
                )

    def evaluate_state_effect(
        self,
        effect: StateEffectSpec,
        before_state: dict[str, Any],
        after_state: dict[str, Any],
        bound_variables: dict[str, Any],
    ) -> tuple[TriState, str | None]:
        """Evaluates an expected StateEffectSpec against before and after state snapshots.

        Returns:
            tuple[TriState, str | None]: (Effect conformance verdict, optional explanation).
        """
        entity_id = bound_variables.get(effect.entity_id_var)
        if entity_id is None:
            return (
                TriState.UNKNOWN,
                f"Entity ID variable '{effect.entity_id_var}' is not bound.",
            )

        # Locate entity records in before and after states
        # Entity states can be structured as {entity_type: {entity_id: {...}}} or flat
        before_entities = before_state.get(effect.entity_type, {})
        after_entities = after_state.get(effect.entity_type, {})

        # Support list or dict representation
        before_record = self._find_entity_record(before_entities, entity_id)
        after_record = self._find_entity_record(after_entities, entity_id)

        match effect.effect_type:
            case EffectType.CREATED:
                if after_record is None:
                    return (
                        TriState.FALSE,
                        f"Entity '{effect.entity_type}:{entity_id}' was not created.",
                    )
                actual_val, missing = extract_context_value(after_record, effect.field)
                if missing:
                    return (
                        TriState.UNKNOWN,
                        f"Created entity '{effect.entity_type}:{entity_id}' missing field '{effect.field}'.",
                    )
                if (
                    effect.expected_value is not None
                    and actual_val != effect.expected_value
                ):
                    return TriState.FALSE, (
                        f"Created entity '{effect.entity_type}:{entity_id}' field '{effect.field}' "
                        f"has value '{actual_val}', expected '{effect.expected_value}'."
                    )
                return TriState.TRUE, None

            case EffectType.UPDATED:
                if after_record is None:
                    return (
                        TriState.FALSE,
                        f"Entity '{effect.entity_type}:{entity_id}' does not exist after transition.",
                    )
                actual_val, missing = extract_context_value(after_record, effect.field)
                if missing:
                    return (
                        TriState.UNKNOWN,
                        f"Entity '{effect.entity_type}:{entity_id}' missing field '{effect.field}' in after state.",
                    )
                if (
                    effect.expected_value is not None
                    and actual_val != effect.expected_value
                ):
                    return TriState.FALSE, (
                        f"Updated entity '{effect.entity_type}:{entity_id}' field '{effect.field}' "
                        f"has value '{actual_val}', expected '{effect.expected_value}'."
                    )
                return TriState.TRUE, None

            case EffectType.DELETED:
                if after_record is not None:
                    return (
                        TriState.FALSE,
                        f"Entity '{effect.entity_type}:{entity_id}' was not deleted.",
                    )
                return TriState.TRUE, None

            case EffectType.UNCHANGED:
                # Protected state verification: before and after values must be identical
                if before_record is None and after_record is None:
                    return TriState.TRUE, None
                if (before_record is None) != (after_record is None):
                    return (
                        TriState.FALSE,
                        f"Entity '{effect.entity_type}:{entity_id}' presence changed unexpectedly.",
                    )
                val_before, miss_before = extract_context_value(
                    before_record, effect.field
                )
                val_after, miss_after = extract_context_value(
                    after_record, effect.field
                )
                if miss_before and miss_after:
                    return TriState.TRUE, None
                if miss_before != miss_after or val_before != val_after:
                    return TriState.FALSE, (
                        f"Protected field '{effect.field}' on entity '{effect.entity_type}:{entity_id}' "
                        f"was modified from '{val_before}' to '{val_after}'."
                    )
                return TriState.TRUE, None

        return TriState.UNKNOWN, "Unhandled effect type"

    @staticmethod
    def _find_entity_record(
        entity_container: Any, entity_id: Any
    ) -> dict[str, Any] | None:
        """Helper to find an entity record by ID in dict or list container."""
        if isinstance(entity_container, dict):
            # Keyed by entity_id: e.g. {503: {...}} or {"503": {...}}
            if entity_id in entity_container:
                return entity_container[entity_id]
            str_id = str(entity_id)
            if str_id in entity_container:
                return entity_container[str_id]
            # Keyed by id field inside record
            for rec in entity_container.values():
                if isinstance(rec, dict) and (
                    rec.get("id") == entity_id or str(rec.get("id")) == str_id
                ):
                    return rec
            return None

        if isinstance(entity_container, list):
            str_id = str(entity_id)
            for item in entity_container:
                if isinstance(item, dict) and (
                    item.get("id") == entity_id or str(item.get("id")) == str_id
                ):
                    return item
            return None

        return None

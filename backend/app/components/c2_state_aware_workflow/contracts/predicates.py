"""Declarative, structured predicates for C2 workflow contracts.

All predicate evaluation is performed via pure, deterministic AST operations.
No user-provided code, dynamic expressions, eval, exec, SQL, or shell commands
are permitted or executed.
"""

from typing import Any, Self
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.components.c2_state_aware_workflow.contracts.enums import (
    EffectType,
    LogicalOperator,
    PredicateOperator,
    TriState,
)


class PredicateEvaluationError(Exception):
    """Base exception for predicate evaluation errors."""


class IncompatibleTypeError(PredicateEvaluationError, TypeError):
    """Raised when operand types are incompatible for a typed comparison."""


class MissingValueError(PredicateEvaluationError, KeyError):
    """Raised when a required observation or variable is missing."""


class UnsupportedOperatorError(PredicateEvaluationError, ValueError):
    """Raised when an unknown or unsupported operator is encountered."""


def extract_context_value(context: Any, field_name: str) -> tuple[Any, bool]:
    """Safely extracts a value from context and identifies if it is MISSING.

    Returns:
        tuple[Any, bool]: (value, is_missing).
        If is_missing is True: the observation is completely absent or marked MISSING.
        If is_missing is False and value is None: the field is EXPLICIT_NULL.
        If is_missing is False and value is not None: the field has a PRESENT concrete value.
    """
    if context is None:
        return None, True

    # Dictionary context lookup
    if isinstance(context, dict):
        if field_name in context:
            raw = context[field_name]
            # Check for ObservedValue wrapper from runtime evidence
            if hasattr(raw, "presence"):
                presence_val = getattr(raw.presence, "value", raw.presence)
                if presence_val == "MISSING":
                    return None, True
                if presence_val == "EXPLICIT_NULL":
                    return None, False
                return getattr(raw, "value", None), False
            if raw is None:
                return None, False
            return raw, False

        # Support dot-notation access: e.g. "order.status"
        if "." in field_name:
            parts = field_name.split(".", 1)
            if parts[0] in context and isinstance(context[parts[0]], dict):
                return extract_context_value(context[parts[0]], parts[1])

        return None, True

    # Object attribute context lookup
    if hasattr(context, field_name):
        raw = getattr(context, field_name)
        if hasattr(raw, "presence"):
            presence_val = getattr(raw.presence, "value", raw.presence)
            if presence_val == "MISSING":
                return None, True
            if presence_val == "EXPLICIT_NULL":
                return None, False
            return getattr(raw, "value", None), False
        return raw, False

    return None, True


class StructuredPredicate(BaseModel):
    """Declarative, structured predicate model.

    Can be either a leaf predicate (field, operator, value) or a composite
    predicate (logical_op, children).
    """

    model_config = ConfigDict(extra="forbid")

    # Leaf predicate attributes
    field: str | None = Field(
        default=None,
        description="Name of the variable or entity field being tested",
    )
    operator: PredicateOperator | None = Field(
        default=None,
        description="Comparison or membership operator",
    )
    value: Any = Field(
        default=None,
        description="Literal value or reference to compare against",
    )
    value_is_var_ref: bool = Field(
        default=False,
        description="If True, 'value' is treated as a variable name whose value is resolved at runtime",
    )

    # Composite predicate attributes
    logical_op: LogicalOperator | None = Field(
        default=None,
        description="Logical combinator (and, or, not) for composite expressions",
    )
    children: list["StructuredPredicate"] | None = Field(
        default=None,
        description="List of child predicates combined by logical_op",
    )

    @model_validator(mode="after")
    def validate_predicate_structure(self) -> Self:
        """Enforces that a predicate is either a valid leaf or a valid composite."""
        is_leaf = self.field is not None or self.operator is not None
        is_composite = self.logical_op is not None or self.children is not None

        if is_leaf and is_composite:
            raise ValueError(
                "Predicate cannot be both a leaf (field/operator) and a composite (logical_op/children)."
            )

        if not is_leaf and not is_composite:
            raise ValueError(
                "Predicate must be either a leaf (specifying 'field' and 'operator') "
                "or a composite (specifying 'logical_op' and 'children')."
            )

        if is_leaf:
            if not self.field or not self.field.strip():
                raise ValueError("Leaf predicate must specify a non-empty 'field'.")
            if self.operator is None:
                raise ValueError("Leaf predicate must specify an 'operator'.")

        if is_composite:
            if self.logical_op is None:
                raise ValueError("Composite predicate must specify 'logical_op'.")
            if not self.children:
                raise ValueError(
                    "Composite predicate must have at least one child in 'children'."
                )
            if self.logical_op == LogicalOperator.NOT and len(self.children) != 1:
                raise ValueError(
                    "Composite 'not' predicate must have exactly one child."
                )

        return self

    def evaluate(
        self,
        context: dict[str, Any] | Any,
        raise_on_type_error: bool = False,
    ) -> TriState:
        """Safely evaluates this structured predicate against a variable/attribute context.

        Implements three-valued predicate logic (TRUE, FALSE, UNKNOWN).
        - Comparing a missing field with null returns UNKNOWN.
        - FALSE AND UNKNOWN returns FALSE.
        - TRUE AND UNKNOWN returns UNKNOWN.
        - TRUE OR UNKNOWN returns TRUE.
        - FALSE OR UNKNOWN returns UNKNOWN.
        - Negating UNKNOWN returns UNKNOWN.

        Pure Python typed comparison only. Zero eval, exec, SQL, or shell execution.
        """
        # Composite evaluation
        if self.logical_op is not None and self.children is not None:
            if self.logical_op == LogicalOperator.AND:
                has_unknown = False
                for child in self.children:
                    res = child.evaluate(
                        context, raise_on_type_error=raise_on_type_error
                    )
                    if res == TriState.FALSE:
                        return TriState.FALSE
                    if res == TriState.UNKNOWN:
                        has_unknown = True
                return TriState.UNKNOWN if has_unknown else TriState.TRUE

            if self.logical_op == LogicalOperator.OR:
                has_unknown = False
                for child in self.children:
                    res = child.evaluate(
                        context, raise_on_type_error=raise_on_type_error
                    )
                    if res == TriState.TRUE:
                        return TriState.TRUE
                    if res == TriState.UNKNOWN:
                        has_unknown = True
                return TriState.UNKNOWN if has_unknown else TriState.FALSE

            if self.logical_op == LogicalOperator.NOT:
                child_res = self.children[0].evaluate(
                    context, raise_on_type_error=raise_on_type_error
                )
                if child_res == TriState.TRUE:
                    return TriState.FALSE
                if child_res == TriState.FALSE:
                    return TriState.TRUE
                return TriState.UNKNOWN

        # Leaf evaluation
        assert self.field is not None, "Leaf predicate must specify 'field'"
        actual_val, actual_is_missing = extract_context_value(context, self.field)

        # Target value resolution
        target_val = self.value
        target_is_missing = False
        if self.value_is_var_ref and isinstance(self.value, str):
            target_val, target_is_missing = extract_context_value(context, self.value)

        # If a field is missing, comparisons with it return UNKNOWN
        # (e.g. comparing a missing field with null returns UNKNOWN)
        if actual_is_missing or target_is_missing:
            return TriState.UNKNOWN

        match self.operator:
            case PredicateOperator.IS_NULL:
                return TriState.TRUE if actual_val is None else TriState.FALSE

            case PredicateOperator.IS_NOT_NULL:
                return TriState.TRUE if actual_val is not None else TriState.FALSE

            case PredicateOperator.EQ:
                if actual_val is None and target_val is None:
                    return TriState.TRUE
                if actual_val is None or target_val is None:
                    return TriState.FALSE
                # Typed comparison: prevent silent bool to int coercion (e.g. True == 1)
                if isinstance(actual_val, bool) != isinstance(target_val, bool):
                    return TriState.FALSE
                return TriState.TRUE if actual_val == target_val else TriState.FALSE

            case PredicateOperator.NEQ:
                if actual_val is None and target_val is None:
                    return TriState.FALSE
                if actual_val is None or target_val is None:
                    return TriState.TRUE
                if isinstance(actual_val, bool) != isinstance(target_val, bool):
                    return TriState.TRUE
                return TriState.TRUE if actual_val != target_val else TriState.FALSE

            case (
                PredicateOperator.GT
                | PredicateOperator.GTE
                | PredicateOperator.LT
                | PredicateOperator.LTE
            ):
                if actual_val is None or target_val is None:
                    if raise_on_type_error:
                        raise IncompatibleTypeError(
                            f"Cannot perform ordered comparison {self.operator.value} with null operand."
                        )
                    return TriState.UNKNOWN

                # Typed check: numbers vs numbers, strings vs strings
                is_actual_num = isinstance(actual_val, (int, float)) and not isinstance(
                    actual_val, bool
                )
                is_target_num = isinstance(target_val, (int, float)) and not isinstance(
                    target_val, bool
                )

                if (is_actual_num and not is_target_num) or (
                    is_target_num and not is_actual_num
                ):
                    if raise_on_type_error:
                        raise IncompatibleTypeError(
                            f"Incompatible types for ordered comparison: {type(actual_val).__name__} and {type(target_val).__name__}"
                        )
                    return TriState.UNKNOWN

                if not is_actual_num and type(actual_val) is not type(target_val):
                    if raise_on_type_error:
                        raise IncompatibleTypeError(
                            f"Incompatible types for ordered comparison: {type(actual_val).__name__} and {type(target_val).__name__}"
                        )
                    return TriState.UNKNOWN

                try:
                    if self.operator == PredicateOperator.GT:
                        return (
                            TriState.TRUE if actual_val > target_val else TriState.FALSE
                        )
                    if self.operator == PredicateOperator.GTE:
                        return (
                            TriState.TRUE
                            if actual_val >= target_val
                            else TriState.FALSE
                        )
                    if self.operator == PredicateOperator.LT:
                        return (
                            TriState.TRUE if actual_val < target_val else TriState.FALSE
                        )
                    if self.operator == PredicateOperator.LTE:
                        return (
                            TriState.TRUE
                            if actual_val <= target_val
                            else TriState.FALSE
                        )
                except TypeError as exc:
                    if raise_on_type_error:
                        raise IncompatibleTypeError(str(exc)) from exc
                    return TriState.UNKNOWN

            case PredicateOperator.IN:
                if target_val is None:
                    return TriState.FALSE
                if not isinstance(target_val, (list, tuple, set, dict, str)):
                    if raise_on_type_error:
                        raise IncompatibleTypeError(
                            f"Operator 'in' requires container target, got {type(target_val).__name__}"
                        )
                    return TriState.UNKNOWN
                try:
                    return TriState.TRUE if actual_val in target_val else TriState.FALSE
                except TypeError as exc:
                    if raise_on_type_error:
                        raise IncompatibleTypeError(str(exc)) from exc
                    return TriState.UNKNOWN

            case PredicateOperator.NOT_IN:
                if target_val is None:
                    return TriState.TRUE
                if not isinstance(target_val, (list, tuple, set, dict, str)):
                    if raise_on_type_error:
                        raise IncompatibleTypeError(
                            f"Operator 'not_in' requires container target, got {type(target_val).__name__}"
                        )
                    return TriState.UNKNOWN
                try:
                    return TriState.FALSE if actual_val in target_val else TriState.TRUE
                except TypeError as exc:
                    if raise_on_type_error:
                        raise IncompatibleTypeError(str(exc)) from exc
                    return TriState.UNKNOWN

            case PredicateOperator.CONTAINS:
                if actual_val is None:
                    return TriState.FALSE
                if not isinstance(actual_val, (list, tuple, set, dict, str)):
                    if raise_on_type_error:
                        raise IncompatibleTypeError(
                            f"Operator 'contains' requires container field, got {type(actual_val).__name__}"
                        )
                    return TriState.UNKNOWN
                try:
                    return TriState.TRUE if target_val in actual_val else TriState.FALSE
                except TypeError as exc:
                    if raise_on_type_error:
                        raise IncompatibleTypeError(str(exc)) from exc
                    return TriState.UNKNOWN

            case PredicateOperator.MATCHES_ENTITY:
                if actual_val is None or target_val is None:
                    return TriState.FALSE
                return TriState.TRUE if actual_val == target_val else TriState.FALSE

            case _:
                if raise_on_type_error:
                    raise UnsupportedOperatorError(
                        f"Unsupported predicate operator: {self.operator}"
                    )
                return TriState.FALSE

    def evaluate_bool(
        self,
        context: dict[str, Any] | Any,
        unknown_as_false: bool = True,
    ) -> bool:
        """Helper to get a standard boolean verdict, treating UNKNOWN as false by default."""
        res = self.evaluate(context)
        if res == TriState.TRUE:
            return True
        if res == TriState.FALSE:
            return False
        return not unknown_as_false


class VariableUpdate(BaseModel):
    """Declarative variable update performed on transition firing."""

    model_config = ConfigDict(extra="forbid")

    variable_name: str = Field(..., description="Target EFSM variable to update")
    operation: str = Field(
        ...,
        description="Operation: 'set', 'increment', 'append', 'bind_entity'",
    )
    source_field: str | None = Field(
        default=None,
        description="Optional field name from event payload or state observation",
    )
    value: Any = Field(
        default=None,
        description="Literal value or default value to apply",
    )


class StateEffectSpec(BaseModel):
    """Specification of expected persistent side effects on domain entities."""

    model_config = ConfigDict(extra="forbid")

    entity_type: str = Field(
        ..., description="Entity type, e.g. 'refund', 'order', 'payment'"
    )
    entity_id_var: str = Field(
        ...,
        description="Variable storing the target entity ID, e.g. 'selected_order_id'",
    )
    field: str = Field(..., description="Entity attribute modified, e.g. 'status'")
    effect_type: EffectType = Field(..., description="Expected mutation type")
    expected_value: Any = Field(
        default=None,
        description="Expected post-transition value (None if deleted or check presence only)",
    )
    description: str | None = Field(
        default=None,
        description="Human-readable explanation of this state effect",
    )

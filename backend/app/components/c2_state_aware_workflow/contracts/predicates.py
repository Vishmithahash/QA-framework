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
)


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

    def evaluate(self, context: dict[str, Any]) -> bool:
        """Safely evaluates this structured predicate against a variable/attribute context.

        Pure Python comparison only. Zero eval, exec, SQL, or shell execution.
        """
        if self.logical_op is not None and self.children is not None:
            if self.logical_op == LogicalOperator.AND:
                return all(child.evaluate(context) for child in self.children)
            if self.logical_op == LogicalOperator.OR:
                return any(child.evaluate(context) for child in self.children)
            if self.logical_op == LogicalOperator.NOT:
                return not self.children[0].evaluate(context)

        # Leaf evaluation
        assert self.field is not None
        actual_val = context.get(self.field)

        target_val = self.value
        if self.value_is_var_ref and isinstance(self.value, str):
            target_val = context.get(self.value)

        match self.operator:
            case PredicateOperator.EQ:
                return actual_val == target_val
            case PredicateOperator.NEQ:
                return actual_val != target_val
            case PredicateOperator.GT:
                if actual_val is None or target_val is None:
                    return False
                return actual_val > target_val
            case PredicateOperator.GTE:
                if actual_val is None or target_val is None:
                    return False
                return actual_val >= target_val
            case PredicateOperator.LT:
                if actual_val is None or target_val is None:
                    return False
                return actual_val < target_val
            case PredicateOperator.LTE:
                if actual_val is None or target_val is None:
                    return False
                return actual_val <= target_val
            case PredicateOperator.IN:
                if target_val is None:
                    return False
                return actual_val in target_val
            case PredicateOperator.NOT_IN:
                if target_val is None:
                    return True
                return actual_val not in target_val
            case PredicateOperator.IS_NULL:
                return actual_val is None
            case PredicateOperator.IS_NOT_NULL:
                return actual_val is not None
            case PredicateOperator.CONTAINS:
                if actual_val is None:
                    return False
                return target_val in actual_val
            case PredicateOperator.MATCHES_ENTITY:
                return actual_val == target_val
            case _:
                return False


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

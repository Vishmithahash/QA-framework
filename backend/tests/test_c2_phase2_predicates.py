"""Tests for three-valued predicate semantics, typed comparisons, and the safe execution engine."""

import pytest
from app.components.c2_state_aware_workflow.contracts.enums import (
    EffectType,
    EvidencePresence,
    LogicalOperator,
    PredicateOperator,
    TriState,
)
from app.components.c2_state_aware_workflow.contracts.predicates import (
    IncompatibleTypeError,
    StateEffectSpec,
    StructuredPredicate,
    VariableUpdate,
)
from app.components.c2_state_aware_workflow.contracts.runtime_evidence import (
    ObservedValue,
)
from app.components.c2_state_aware_workflow.services.predicate_engine import (
    SafePredicateEngine,
    ScopedExecutionContext,
)


class TestTriStateLogic:
    """Verifies mathematical properties of Kleene three-valued logic."""

    def test_tristate_boolean_properties(self):
        assert TriState.TRUE.is_true
        assert not TriState.TRUE.is_false
        assert not TriState.TRUE.is_unknown
        assert bool(TriState.TRUE) is True

        assert TriState.FALSE.is_false
        assert not TriState.FALSE.is_true
        assert not TriState.FALSE.is_unknown
        assert bool(TriState.FALSE) is False

        assert TriState.UNKNOWN.is_unknown
        assert not TriState.UNKNOWN.is_true
        assert not TriState.UNKNOWN.is_false

        # Coercing UNKNOWN directly to boolean raises TypeError to prevent silent bugs
        with pytest.raises(
            TypeError, match="Cannot evaluate UNKNOWN TriState as boolean"
        ):
            bool(TriState.UNKNOWN)

    def test_and_truth_table(self):
        # FALSE AND UNKNOWN -> FALSE
        assert (TriState.FALSE & TriState.UNKNOWN) == TriState.FALSE
        assert (TriState.UNKNOWN & TriState.FALSE) == TriState.FALSE

        # TRUE AND UNKNOWN -> UNKNOWN
        assert (TriState.TRUE & TriState.UNKNOWN) == TriState.UNKNOWN
        assert (TriState.UNKNOWN & TriState.TRUE) == TriState.UNKNOWN

        # TRUE AND TRUE -> TRUE
        assert (TriState.TRUE & TriState.TRUE) == TriState.TRUE

        # FALSE AND FALSE -> FALSE
        assert (TriState.FALSE & TriState.FALSE) == TriState.FALSE

        # UNKNOWN AND UNKNOWN -> UNKNOWN
        assert (TriState.UNKNOWN & TriState.UNKNOWN) == TriState.UNKNOWN

    def test_or_truth_table(self):
        # TRUE OR UNKNOWN -> TRUE
        assert (TriState.TRUE | TriState.UNKNOWN) == TriState.TRUE
        assert (TriState.UNKNOWN | TriState.TRUE) == TriState.TRUE

        # FALSE OR UNKNOWN -> UNKNOWN
        assert (TriState.FALSE | TriState.UNKNOWN) == TriState.UNKNOWN
        assert (TriState.UNKNOWN | TriState.FALSE) == TriState.UNKNOWN

        # TRUE OR TRUE -> TRUE
        assert (TriState.TRUE | TriState.TRUE) == TriState.TRUE

        # FALSE OR FALSE -> FALSE
        assert (TriState.FALSE | TriState.FALSE) == TriState.FALSE

        # UNKNOWN OR UNKNOWN -> UNKNOWN
        assert (TriState.UNKNOWN | TriState.UNKNOWN) == TriState.UNKNOWN

    def test_not_truth_table(self):
        # Negating UNKNOWN -> UNKNOWN
        assert (~TriState.UNKNOWN) == TriState.UNKNOWN
        assert (~TriState.TRUE) == TriState.FALSE
        assert (~TriState.FALSE) == TriState.TRUE


class TestMissingVsExplicitNullVsFalse:
    """Verifies that missing observations remain strictly distinct from explicit null and false."""

    def test_missing_field_comparison_returns_unknown(self):
        ctx = {"order_id": 503}  # "notes" is missing

        pred_null = StructuredPredicate(
            field="notes", operator=PredicateOperator.IS_NULL
        )
        assert pred_null.evaluate(ctx) == TriState.UNKNOWN

        pred_not_null = StructuredPredicate(
            field="notes", operator=PredicateOperator.IS_NOT_NULL
        )
        assert pred_not_null.evaluate(ctx) == TriState.UNKNOWN

        pred_eq = StructuredPredicate(
            field="notes", operator=PredicateOperator.EQ, value="urgent"
        )
        assert pred_eq.evaluate(ctx) == TriState.UNKNOWN

    def test_observed_value_missing_returns_unknown(self):
        ctx = {
            "notes": ObservedValue(value=None, presence=EvidencePresence.MISSING),
        }
        pred = StructuredPredicate(field="notes", operator=PredicateOperator.IS_NULL)
        assert pred.evaluate(ctx) == TriState.UNKNOWN

    def test_explicit_null_semantics(self):
        ctx = {"notes": None}  # Explicit null

        pred_is_null = StructuredPredicate(
            field="notes", operator=PredicateOperator.IS_NULL
        )
        assert pred_is_null.evaluate(ctx) == TriState.TRUE

        pred_not_null = StructuredPredicate(
            field="notes", operator=PredicateOperator.IS_NOT_NULL
        )
        assert pred_not_null.evaluate(ctx) == TriState.FALSE

        pred_eq_none = StructuredPredicate(
            field="notes", operator=PredicateOperator.EQ, value=None
        )
        assert pred_eq_none.evaluate(ctx) == TriState.TRUE

        pred_eq_val = StructuredPredicate(
            field="notes", operator=PredicateOperator.EQ, value="test"
        )
        assert pred_eq_val.evaluate(ctx) == TriState.FALSE

    def test_observed_value_explicit_null_semantics(self):
        ctx = {
            "notes": ObservedValue(value=None, presence=EvidencePresence.EXPLICIT_NULL),
        }
        pred_is_null = StructuredPredicate(
            field="notes", operator=PredicateOperator.IS_NULL
        )
        assert pred_is_null.evaluate(ctx) == TriState.TRUE

    def test_false_value_distinction(self):
        ctx = {"is_verified": False}  # Concrete false value

        pred_eq_false = StructuredPredicate(
            field="is_verified", operator=PredicateOperator.EQ, value=False
        )
        assert pred_eq_false.evaluate(ctx) == TriState.TRUE

        pred_is_null = StructuredPredicate(
            field="is_verified", operator=PredicateOperator.IS_NULL
        )
        assert pred_is_null.evaluate(ctx) == TriState.FALSE

        pred_eq_none = StructuredPredicate(
            field="is_verified", operator=PredicateOperator.EQ, value=None
        )
        assert pred_eq_none.evaluate(ctx) == TriState.FALSE

        # False is distinct from 0 under typed comparison
        pred_eq_zero = StructuredPredicate(
            field="is_verified", operator=PredicateOperator.EQ, value=0
        )
        assert pred_eq_zero.evaluate(ctx) == TriState.FALSE


class TestCompositePredicatesWithThreeValuedLogic:
    """Verifies composite AND/OR/NOT evaluation under Kleene three-valued semantics."""

    def test_composite_and_with_unknown(self):
        ctx = {"a": True}  # "b" is missing

        # TRUE AND UNKNOWN -> UNKNOWN
        p_and = StructuredPredicate(
            logical_op=LogicalOperator.AND,
            children=[
                StructuredPredicate(
                    field="a", operator=PredicateOperator.EQ, value=True
                ),
                StructuredPredicate(
                    field="b", operator=PredicateOperator.EQ, value=True
                ),
            ],
        )
        assert p_and.evaluate(ctx) == TriState.UNKNOWN

        # FALSE AND UNKNOWN -> FALSE
        p_false_and = StructuredPredicate(
            logical_op=LogicalOperator.AND,
            children=[
                StructuredPredicate(
                    field="a", operator=PredicateOperator.EQ, value=False
                ),  # False
                StructuredPredicate(
                    field="b", operator=PredicateOperator.EQ, value=True
                ),  # Unknown
            ],
        )
        assert p_false_and.evaluate(ctx) == TriState.FALSE

    def test_composite_or_with_unknown(self):
        ctx = {"a": True}  # "b" is missing

        # TRUE OR UNKNOWN -> TRUE
        p_or = StructuredPredicate(
            logical_op=LogicalOperator.OR,
            children=[
                StructuredPredicate(
                    field="a", operator=PredicateOperator.EQ, value=True
                ),  # True
                StructuredPredicate(
                    field="b", operator=PredicateOperator.EQ, value=True
                ),  # Unknown
            ],
        )
        assert p_or.evaluate(ctx) == TriState.TRUE

        # FALSE OR UNKNOWN -> UNKNOWN
        p_false_or = StructuredPredicate(
            logical_op=LogicalOperator.OR,
            children=[
                StructuredPredicate(
                    field="a", operator=PredicateOperator.EQ, value=False
                ),  # False
                StructuredPredicate(
                    field="b", operator=PredicateOperator.EQ, value=True
                ),  # Unknown
            ],
        )
        assert p_false_or.evaluate(ctx) == TriState.UNKNOWN

    def test_composite_not_with_unknown(self):
        ctx = {}  # "b" is missing
        p_not = StructuredPredicate(
            logical_op=LogicalOperator.NOT,
            children=[
                StructuredPredicate(
                    field="b", operator=PredicateOperator.EQ, value=True
                ),
            ],
        )
        assert p_not.evaluate(ctx) == TriState.UNKNOWN


class TestTypedComparisons:
    """Verifies typed comparison behavior and explicit type mismatch reporting."""

    def test_incompatible_ordered_types_raises_error(self):
        ctx = {"amount": "89.0"}  # String instead of float/int

        pred = StructuredPredicate(
            field="amount", operator=PredicateOperator.GT, value=50.0
        )
        with pytest.raises(
            IncompatibleTypeError, match="Incompatible types for ordered comparison"
        ):
            pred.evaluate(ctx, raise_on_type_error=True)

        # Non-raising mode returns UNKNOWN
        assert pred.evaluate(ctx, raise_on_type_error=False) == TriState.UNKNOWN

    def test_incompatible_collection_target_raises_error(self):
        pred = StructuredPredicate(field="x", operator=PredicateOperator.IN, value=123)
        with pytest.raises(IncompatibleTypeError, match="requires container target"):
            pred.evaluate({"x": 1}, raise_on_type_error=True)


class TestSafePredicateEngine:
    """Verifies ScopedExecutionContext and SafePredicateEngine functionality."""

    def test_scoped_resolution(self):
        engine = SafePredicateEngine()
        context = ScopedExecutionContext(
            event_data={"order_id": 503, "amount": 89.0},
            bound_variables={"selected_order_id": 503, "customer_id": 42},
            fixture_context={"customer_email": "cust42@test.internal"},
            before_state={"order": {"503": {"status": "PAID"}}},
            after_state={"order": {"503": {"status": "REFUNDED"}}},
        )

        pred1 = StructuredPredicate(
            field="event.order_id", operator=PredicateOperator.EQ, value=503
        )
        assert engine.evaluate_predicate(pred1, context) == TriState.TRUE

        pred2 = StructuredPredicate(
            field="var.selected_order_id", operator=PredicateOperator.EQ, value=503
        )
        assert engine.evaluate_predicate(pred2, context) == TriState.TRUE

        # Flat search finds selected_order_id in bound_variables
        pred3 = StructuredPredicate(
            field="customer_id", operator=PredicateOperator.EQ, value=42
        )
        assert engine.evaluate_predicate(pred3, context) == TriState.TRUE

    def test_declarative_variable_updates(self):
        engine = SafePredicateEngine()
        context = ScopedExecutionContext(
            event_data={"new_order_id": 503, "count": 2},
            bound_variables={"counter": 10, "items": ["a"]},
        )

        # bind_entity
        up1 = VariableUpdate(
            variable_name="selected_order_id",
            operation="bind_entity",
            source_field="event.new_order_id",
        )
        engine.apply_variable_update(up1, context)
        assert context.bound_variables["selected_order_id"] == 503

        # increment
        up2 = VariableUpdate(
            variable_name="counter",
            operation="increment",
            value=5,
        )
        engine.apply_variable_update(up2, context)
        assert context.bound_variables["counter"] == 15

        # append
        up3 = VariableUpdate(
            variable_name="items",
            operation="append",
            value="b",
        )
        engine.apply_variable_update(up3, context)
        assert context.bound_variables["items"] == ["a", "b"]

    def test_state_effect_verification(self):
        engine = SafePredicateEngine()
        before = {
            "order": {503: {"id": 503, "payment_status": "PAID"}},
            "refund": {},
        }
        after = {
            "order": {503: {"id": 503, "payment_status": "REFUNDED"}},
            "refund": {503: {"id": 503, "status": "COMPLETED"}},
        }
        bound = {"selected_order_id": 503}

        # Updated effect
        eff_order = StateEffectSpec(
            entity_type="order",
            entity_id_var="selected_order_id",
            field="payment_status",
            effect_type=EffectType.UPDATED,
            expected_value="REFUNDED",
        )
        res, msg = engine.evaluate_state_effect(eff_order, before, after, bound)
        assert res == TriState.TRUE

        # Created effect
        eff_refund = StateEffectSpec(
            entity_type="refund",
            entity_id_var="selected_order_id",
            field="status",
            effect_type=EffectType.CREATED,
            expected_value="COMPLETED",
        )
        res, msg = engine.evaluate_state_effect(eff_refund, before, after, bound)
        assert res == TriState.TRUE

        # Unchanged effect (protected state check)
        eff_unchanged = StateEffectSpec(
            entity_type="order",
            entity_id_var="selected_order_id",
            field="payment_status",
            effect_type=EffectType.UNCHANGED,
        )
        res, msg = engine.evaluate_state_effect(eff_unchanged, before, after, bound)
        assert res == TriState.FALSE  # It was changed from PAID to REFUNDED

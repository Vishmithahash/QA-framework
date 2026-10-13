"""Unit tests for C4 safe deterministic predicate engine and 3-valued logic."""

from decimal import Decimal
from app.components.c4_policy_aware_safety.contracts.predicates import (
    AtomicPredicate,
    CompoundPredicate,
    PredicateOperator,
    PredicateResult,
)
from app.components.c4_policy_aware_safety.predicates.engine import SafePredicateEngine


def test_missing_field_returns_unknown():
    """Missing evidence field must evaluate to UNKNOWN, not False or None."""
    pred = AtomicPredicate(
        field="user.department", operator=PredicateOperator.EQ, value="Finance"
    )
    evidence = {"user": {"name": "Alice"}}
    missing = []
    result = SafePredicateEngine.evaluate(pred, evidence, missing)

    assert result == PredicateResult.UNKNOWN
    assert "user.department" in missing


def test_distinguish_missing_from_false_and_zero_and_null():
    """Preserve exact distinction between missing, explicit null, False, 0, and empty collections."""
    # 1. Explicit False vs Missing
    pred_eq_false = AtomicPredicate(
        field="approved", operator=PredicateOperator.EQ, value=False
    )
    evidence_with_false = {"approved": False}
    evidence_missing = {}

    assert (
        SafePredicateEngine.evaluate(pred_eq_false, evidence_with_false)
        == PredicateResult.TRUE
    )
    assert (
        SafePredicateEngine.evaluate(pred_eq_false, evidence_missing)
        == PredicateResult.UNKNOWN
    )

    # 2. Explicit 0 vs Missing vs False
    pred_eq_zero = AtomicPredicate(
        field="count", operator=PredicateOperator.EQ, value=0
    )
    assert (
        SafePredicateEngine.evaluate(pred_eq_zero, {"count": 0}) == PredicateResult.TRUE
    )
    assert (
        SafePredicateEngine.evaluate(pred_eq_zero, {"count": False})
        == PredicateResult.FALSE
    )
    assert SafePredicateEngine.evaluate(pred_eq_zero, {}) == PredicateResult.UNKNOWN

    # 3. Explicit Null vs Missing
    pred_is_null = AtomicPredicate(
        field="manager_id", operator=PredicateOperator.IS_NULL
    )
    assert (
        SafePredicateEngine.evaluate(pred_is_null, {"manager_id": None})
        == PredicateResult.TRUE
    )
    assert (
        SafePredicateEngine.evaluate(pred_is_null, {"manager_id": "mgr_123"})
        == PredicateResult.FALSE
    )
    assert SafePredicateEngine.evaluate(pred_is_null, {}) == PredicateResult.UNKNOWN

    # 4. Presence check
    pred_exists = AtomicPredicate(field="items", operator=PredicateOperator.EXISTS)
    assert (
        SafePredicateEngine.evaluate(pred_exists, {"items": []}) == PredicateResult.TRUE
    )
    assert SafePredicateEngine.evaluate(pred_exists, {}) == PredicateResult.FALSE


def test_numeric_comparisons_minor_units_and_decimals():
    """Verify ordered comparisons using integer minor units and Decimal precision."""
    pred_gt = AtomicPredicate(field="amount", operator=PredicateOperator.GT, value=5000)

    # Integer minor units comparison
    assert (
        SafePredicateEngine.evaluate(pred_gt, {"amount": 7500}) == PredicateResult.TRUE
    )
    assert (
        SafePredicateEngine.evaluate(pred_gt, {"amount": 5000}) == PredicateResult.FALSE
    )
    assert (
        SafePredicateEngine.evaluate(pred_gt, {"amount": 4999}) == PredicateResult.FALSE
    )

    # Decimal comparison
    pred_lte_dec = AtomicPredicate(
        field="price", operator=PredicateOperator.LTE, value="99.99"
    )
    assert (
        SafePredicateEngine.evaluate(pred_lte_dec, {"price": Decimal("50.00")})
        == PredicateResult.TRUE
    )
    assert (
        SafePredicateEngine.evaluate(pred_lte_dec, {"price": Decimal("100.00")})
        == PredicateResult.FALSE
    )


def test_membership_and_null_handling():
    """Membership checks with in and not_in."""
    pred_in = AtomicPredicate(
        field="role", operator=PredicateOperator.IN, value=["ADMIN", "MANAGER"]
    )
    assert (
        SafePredicateEngine.evaluate(pred_in, {"role": "MANAGER"})
        == PredicateResult.TRUE
    )
    assert (
        SafePredicateEngine.evaluate(pred_in, {"role": "SUPPORT"})
        == PredicateResult.FALSE
    )
    assert SafePredicateEngine.evaluate(pred_in, {}) == PredicateResult.UNKNOWN


def test_compound_predicates_kleene_logic():
    """Verify ALL, ANY, NOT combinators under 3-valued Kleene logic."""
    p_true = AtomicPredicate(field="a", operator=PredicateOperator.EQ, value=1)
    p_false = AtomicPredicate(field="b", operator=PredicateOperator.EQ, value=2)
    p_unknown = AtomicPredicate(field="c", operator=PredicateOperator.EQ, value=3)

    evidence = {"a": 1, "b": 999}  # c is missing -> UNKNOWN

    # ALL (AND): False and anything -> False; True and Unknown -> Unknown
    comp_all_false = CompoundPredicate(
        operator=PredicateOperator.ALL, predicates=[p_true, p_false, p_unknown]
    )
    assert (
        SafePredicateEngine.evaluate(comp_all_false, evidence) == PredicateResult.FALSE
    )

    comp_all_unk = CompoundPredicate(
        operator=PredicateOperator.ALL, predicates=[p_true, p_unknown]
    )
    assert (
        SafePredicateEngine.evaluate(comp_all_unk, evidence) == PredicateResult.UNKNOWN
    )

    comp_all_true = CompoundPredicate(
        operator=PredicateOperator.ALL, predicates=[p_true]
    )
    assert SafePredicateEngine.evaluate(comp_all_true, evidence) == PredicateResult.TRUE

    # ANY (OR): True or anything -> True; False or Unknown -> Unknown
    comp_any_true = CompoundPredicate(
        operator=PredicateOperator.ANY, predicates=[p_false, p_true, p_unknown]
    )
    assert SafePredicateEngine.evaluate(comp_any_true, evidence) == PredicateResult.TRUE

    comp_any_unk = CompoundPredicate(
        operator=PredicateOperator.ANY, predicates=[p_false, p_unknown]
    )
    assert (
        SafePredicateEngine.evaluate(comp_any_unk, evidence) == PredicateResult.UNKNOWN
    )

    # NOT
    comp_not_true = CompoundPredicate(
        operator=PredicateOperator.NOT, predicates=[p_true]
    )
    assert (
        SafePredicateEngine.evaluate(comp_not_true, evidence) == PredicateResult.FALSE
    )

    comp_not_unk = CompoundPredicate(
        operator=PredicateOperator.NOT, predicates=[p_unknown]
    )
    assert (
        SafePredicateEngine.evaluate(comp_not_unk, evidence) == PredicateResult.UNKNOWN
    )

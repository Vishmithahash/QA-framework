"""Safe deterministic 3-valued predicate engine for C4."""

from decimal import Decimal, InvalidOperation
from typing import Any
from pydantic import BaseModel
from app.components.c4_policy_aware_safety.contracts.predicates import (
    AtomicPredicate,
    CompoundPredicate,
    DeclarativePredicate,
    PredicateOperator,
    PredicateResult,
)

# Marker for fields that are completely absent from the evidence dictionary
_MISSING_SENTINEL = object()


class SafePredicateEngine:
    """
    Deterministic predicate evaluation using 3-valued logic (TRUE, FALSE, UNKNOWN).
    Strictly forbids eval/exec. Accurately preserves distinctions between missing,
    None, False, 0, and empty collections.
    """

    @classmethod
    def get_field_value(cls, data: Any, field_path: str) -> tuple[Any, bool]:
        """
        Extract field from nested dictionary or Pydantic model using dot-path notation.
        Returns (value, is_present: bool).
        """
        if data is None:
            return _MISSING_SENTINEL, False

        parts = field_path.split(".")
        current = data

        for part in parts:
            if isinstance(current, dict):
                if part in current:
                    current = current[part]
                else:
                    return _MISSING_SENTINEL, False
            elif isinstance(current, BaseModel):
                if hasattr(current, part):
                    current = getattr(current, part)
                else:
                    return _MISSING_SENTINEL, False
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return _MISSING_SENTINEL, False

        return current, True

    @classmethod
    def _coerce_numeric(cls, val: Any) -> Decimal | None:
        """Coerce numeric values to Decimal to avoid binary float imprecision."""
        if val is None or isinstance(val, bool):
            return None
        if isinstance(val, (int, float, Decimal)):
            try:
                return Decimal(str(val))
            except (InvalidOperation, ValueError):
                return None
        if isinstance(val, str):
            try:
                return Decimal(val.strip())
            except (InvalidOperation, ValueError):
                return None
        return None

    @classmethod
    def evaluate_atomic(
        cls,
        predicate: AtomicPredicate,
        evidence: Any,
        missing_fields: list[str] | None = None,
    ) -> PredicateResult:
        """Evaluate a single atomic predicate against evidence."""
        val, is_present = cls.get_field_value(evidence, predicate.field)

        op = predicate.operator
        target = predicate.value

        # Handle presence operators first
        if op == PredicateOperator.EXISTS:
            return PredicateResult.TRUE if is_present else PredicateResult.FALSE
        if op == PredicateOperator.NOT_EXISTS:
            return PredicateResult.FALSE if is_present else PredicateResult.TRUE

        # If field is absent from evidence, decision is UNKNOWN for all other operators
        if not is_present:
            if missing_fields is not None:
                missing_fields.append(predicate.field)
            return PredicateResult.UNKNOWN

        # Handle explicit nullability checks
        if op == PredicateOperator.IS_NULL:
            return PredicateResult.TRUE if val is None else PredicateResult.FALSE
        if op == PredicateOperator.IS_NOT_NULL:
            return PredicateResult.TRUE if val is not None else PredicateResult.FALSE

        # Equality
        if op == PredicateOperator.EQ:
            # Preserve strict distinction between boolean (e.g. False) and numeric zero (0)
            if isinstance(val, bool) != isinstance(target, bool):
                return PredicateResult.FALSE
            num_val = cls._coerce_numeric(val)
            num_target = cls._coerce_numeric(target)
            if num_val is not None and num_target is not None:
                return PredicateResult.from_bool(num_val == num_target)
            return PredicateResult.from_bool(val == target)

        if op == PredicateOperator.NEQ:
            if isinstance(val, bool) != isinstance(target, bool):
                return PredicateResult.TRUE
            num_val = cls._coerce_numeric(val)
            num_target = cls._coerce_numeric(target)
            if num_val is not None and num_target is not None:
                return PredicateResult.from_bool(num_val != num_target)
            return PredicateResult.from_bool(val != target)

        # Ordered comparisons
        if op in (
            PredicateOperator.LT,
            PredicateOperator.LTE,
            PredicateOperator.GT,
            PredicateOperator.GTE,
        ):
            if val is None or target is None:
                # Cannot order-compare nulls
                return PredicateResult.UNKNOWN

            num_val = cls._coerce_numeric(val)
            num_target = cls._coerce_numeric(target)

            if num_val is not None and num_target is not None:
                if op == PredicateOperator.LT:
                    return PredicateResult.from_bool(num_val < num_target)
                if op == PredicateOperator.LTE:
                    return PredicateResult.from_bool(num_val <= num_target)
                if op == PredicateOperator.GT:
                    return PredicateResult.from_bool(num_val > num_target)
                if op == PredicateOperator.GTE:
                    return PredicateResult.from_bool(num_val >= num_target)

            try:
                if op == PredicateOperator.LT:
                    return PredicateResult.from_bool(val < target)
                if op == PredicateOperator.LTE:
                    return PredicateResult.from_bool(val <= target)
                if op == PredicateOperator.GT:
                    return PredicateResult.from_bool(val > target)
                if op == PredicateOperator.GTE:
                    return PredicateResult.from_bool(val >= target)
            except TypeError:
                return PredicateResult.UNKNOWN

        # Membership
        if op == PredicateOperator.IN:
            if target is None or not isinstance(target, (list, tuple, set, str)):
                return PredicateResult.UNKNOWN
            try:
                return PredicateResult.from_bool(val in target)
            except TypeError:
                return PredicateResult.UNKNOWN

        if op == PredicateOperator.NOT_IN:
            if target is None or not isinstance(target, (list, tuple, set, str)):
                return PredicateResult.UNKNOWN
            try:
                return PredicateResult.from_bool(val not in target)
            except TypeError:
                return PredicateResult.UNKNOWN

        return PredicateResult.UNKNOWN

    @classmethod
    def evaluate_compound(
        cls,
        predicate: CompoundPredicate,
        evidence: Any,
        missing_fields: list[str] | None = None,
    ) -> PredicateResult:
        """Evaluate compound logical combinator using Kleene 3-valued logic."""
        op = predicate.operator
        children = predicate.predicates

        if not children:
            return PredicateResult.UNKNOWN

        if op == PredicateOperator.NOT:
            first_res = cls.evaluate(children[0], evidence, missing_fields)
            return first_res.negate()

        results = [cls.evaluate(child, evidence, missing_fields) for child in children]

        if op == PredicateOperator.ALL:
            # AND: Any FALSE makes it FALSE. If all TRUE -> TRUE. Otherwise UNKNOWN.
            if any(r == PredicateResult.FALSE for r in results):
                return PredicateResult.FALSE
            if all(r == PredicateResult.TRUE for r in results):
                return PredicateResult.TRUE
            return PredicateResult.UNKNOWN

        if op == PredicateOperator.ANY:
            # OR: Any TRUE makes it TRUE. If all FALSE -> FALSE. Otherwise UNKNOWN.
            if any(r == PredicateResult.TRUE for r in results):
                return PredicateResult.TRUE
            if all(r == PredicateResult.FALSE for r in results):
                return PredicateResult.FALSE
            return PredicateResult.UNKNOWN

        return PredicateResult.UNKNOWN

    @classmethod
    def evaluate(
        cls,
        predicate: DeclarativePredicate | None,
        evidence: Any,
        missing_fields: list[str] | None = None,
    ) -> PredicateResult:
        """Evaluate any DeclarativePredicate (atomic or compound). None evaluates to TRUE."""
        if predicate is None:
            return PredicateResult.TRUE

        if isinstance(predicate, AtomicPredicate):
            return cls.evaluate_atomic(predicate, evidence, missing_fields)
        if isinstance(predicate, CompoundPredicate):
            return cls.evaluate_compound(predicate, evidence, missing_fields)

        return PredicateResult.UNKNOWN

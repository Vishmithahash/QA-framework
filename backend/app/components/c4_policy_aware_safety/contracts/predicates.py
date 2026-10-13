"""Safe declarative predicate contracts for C4 deterministic evaluation."""

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class PredicateResult(str, Enum):
    """Three-valued predicate truth values."""

    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_bool(cls, val: bool | None) -> "PredicateResult":
        if val is None:
            return cls.UNKNOWN
        return cls.TRUE if val else cls.FALSE

    def negate(self) -> "PredicateResult":
        if self == PredicateResult.TRUE:
            return PredicateResult.FALSE
        if self == PredicateResult.FALSE:
            return PredicateResult.TRUE
        return PredicateResult.UNKNOWN


class PredicateOperator(str, Enum):
    """Allowlisted safe comparison, presence, and logical operators."""

    # Comparison
    EQ = "=="
    NEQ = "!="
    LT = "<"
    LTE = "<="
    GT = ">"
    GTE = ">="

    # Membership
    IN = "in"
    NOT_IN = "not_in"

    # Presence & Nullability
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"

    # Logical combinators
    ALL = "all"
    ANY = "any"
    NOT = "not"


class AtomicPredicate(BaseModel):
    """Safe atomic field comparison against allowlisted operator and literal value."""

    field: str = Field(..., description="Allowlisted dot-separated evidence field path")
    operator: PredicateOperator = Field(..., description="Safe predicate operator")
    value: Any = Field(
        default=None,
        description="Literal operand (int, Decimal string, bool, str, list)",
    )


class CompoundPredicate(BaseModel):
    """Safe logical composition of child predicates."""

    operator: PredicateOperator = Field(
        ...,
        description="Logical combinator: must be 'all', 'any', or 'not'",
    )
    predicates: list["DeclarativePredicate"] = Field(
        default_factory=list,
        description="Child predicates evaluated according to 3-valued Kleene logic",
    )


DeclarativePredicate = AtomicPredicate | CompoundPredicate

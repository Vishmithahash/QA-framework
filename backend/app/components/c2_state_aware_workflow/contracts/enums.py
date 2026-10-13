"""Enumerations for Component 2: State-Aware Multi-Step Workflow Testing.

Defines lifecycle statuses, exact evaluation verdicts, reason codes,
predicate operators, mutation categories, and evidence presence types.
"""

from enum import Enum


class LifecycleStatus(str, Enum):
    """Lifecycle stages for workflow models.

    All models created in Phase 1 must remain DRAFT.
    """

    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"


class EvaluationVerdict(str, Enum):
    """Exact six verdicts mandated by Component 2 requirements.

    - PASS: The execution path conformed fully to the reference model.
    - EXPECTED REJECTION PASS: The agent correctly rejected an invalid request,
      preserving protected system state.
    - FAIL: The agent violated a workflow transition, guard, invariant,
      entity continuity, or expected state effect.
    - INCONCLUSIVE: Essential observation or state evidence was missing;
      conformance could not be determined.
    - MODEL NOT READY: The reference model contains contradictions, unreachable
      states, or missing transitions.
    - TEST NOT READY: The generated test case is infeasible, ambiguous, or lacks
      necessary fixture definitions.
    """

    PASS = "PASS"
    EXPECTED_REJECTION_PASS = "EXPECTED REJECTION PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    MODEL_NOT_READY = "MODEL NOT READY"
    TEST_NOT_READY = "TEST NOT READY"


class ReasonCode(str, Enum):
    """Standardized reason codes explaining evaluation verdicts."""

    # Success reasons
    OUTCOME_ACHIEVED = "OUTCOME_ACHIEVED"
    EXPECTED_REJECTION_ENFORCED = "EXPECTED_REJECTION_ENFORCED"

    # Conformance failure reasons
    OUTCOME_NOT_MET = "OUTCOME_NOT_MET"
    INVALID_TRANSITION = "INVALID_TRANSITION"
    GUARD_VIOLATION = "GUARD_VIOLATION"
    INVARIANT_VIOLATION = "INVARIANT_VIOLATION"
    ENTITY_CONTINUITY_BROKEN = "ENTITY_CONTINUITY_BROKEN"
    MISSING_STATE_EFFECT = "MISSING_STATE_EFFECT"
    UNINTENDED_STATE_MODIFICATION = "UNINTENDED_STATE_MODIFICATION"
    PROTECTED_FIELD_MODIFIED = "PROTECTED_FIELD_MODIFIED"
    PREMATURE_TERMINATION = "PREMATURE_TERMINATION"
    REORDERED_STEP_DETECTED = "REORDERED_STEP_DETECTED"
    REPEATED_STEP_DETECTED = "REPEATED_STEP_DETECTED"

    # Evidence and observation issues
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    MISSING_OBSERVATION = "MISSING_OBSERVATION"
    CORRUPTED_TRACE = "CORRUPTED_TRACE"

    # Model readiness issues
    MODEL_NOT_READY_UNREACHABLE_STATE = "MODEL_NOT_READY_UNREACHABLE_STATE"
    MODEL_NOT_READY_CONTRADICTORY_RULES = "MODEL_NOT_READY_CONTRADICTORY_RULES"
    MODEL_NOT_READY_MISSING_TRANSITIONS = "MODEL_NOT_READY_MISSING_TRANSITIONS"
    MODEL_NOT_READY_INVALID_GUARD = "MODEL_NOT_READY_INVALID_GUARD"
    MODEL_NOT_READY_INCOMPLETE_MODEL = "MODEL_NOT_READY_INCOMPLETE_MODEL"

    # Test readiness issues
    TEST_NOT_READY_INFEASIBLE_PATH = "TEST_NOT_READY_INFEASIBLE_PATH"
    TEST_NOT_READY_AMBIGUOUS_FIXTURE = "TEST_NOT_READY_AMBIGUOUS_FIXTURE"
    TEST_NOT_READY_UNRESOLVED_VARIABLE = "TEST_NOT_READY_UNRESOLVED_VARIABLE"


class PredicateOperator(str, Enum):
    """Declarative predicate operators.

    Expressions are evaluated using structured AST evaluation without eval/exec.
    """

    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    CONTAINS = "contains"
    MATCHES_ENTITY = "matches_entity"


class LogicalOperator(str, Enum):
    """Logical combinators for composite predicates."""

    AND = "and"
    OR = "or"
    NOT = "not"


class TestCategory(str, Enum):
    """Categories of generated workflow test cases."""

    NORMAL = "NORMAL"
    ALTERNATIVE = "ALTERNATIVE"
    NEGATIVE = "NEGATIVE"
    MUTATED = "MUTATED"


TestCategory.__test__ = False


class MutationType(str, Enum):
    """Labelled workflow mutations from the C2 mutation catalogue."""

    SKIPPED_STEP = "SKIPPED_STEP"
    REORDERED_STEP = "REORDERED_STEP"
    REPEATED_STEP = "REPEATED_STEP"
    ILLEGAL_TRANSITION = "ILLEGAL_TRANSITION"
    WRONG_ENTITY = "WRONG_ENTITY"
    MISSING_EFFECT = "MISSING_EFFECT"


class EvidencePresence(str, Enum):
    """Distinguishes observed concrete values, explicit nulls, and missing evidence.

    - PRESENT: An observation was captured and contains a concrete value.
    - EXPLICIT_NULL: The field was inspected and is verified to be explicitly null/None in system state.
    - MISSING: No observation was recorded for this field (query failed, omitted, or unobserved).
    """

    PRESENT = "PRESENT"
    EXPLICIT_NULL = "EXPLICIT_NULL"
    MISSING = "MISSING"


class EffectType(str, Enum):
    """Type of state mutation expected or verified."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    UNCHANGED = "unchanged"


class TestReadinessStatus(str, Enum):
    """Readiness status for generated tests."""

    READY = "READY"
    TEST_NOT_READY = "TEST_NOT_READY"


TestReadinessStatus.__test__ = False

"""Base types, enums, and sentinel markers for C1."""

from enum import Enum
from typing import Any


class ExplicitNullType:
    """Sentinel class representing an explicitly recorded JSON null / None value.

    This strictly distinguishes an explicitly recorded null value from missing or
    omitted evidence in runtime traces and assertions.
    """

    _instance = None

    def __new__(cls) -> "ExplicitNullType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "ExplicitNull"

    def __str__(self) -> str:
        return "null"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, ExplicitNullType)

    def __hash__(self) -> int:
        return hash("ExplicitNull")


ExplicitNull = ExplicitNullType()


class ExecutionStatus(str, Enum):
    """Runtime execution statuses from shared agent execution framework."""

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    INTERRUPTED = "INTERRUPTED"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"


class CaseReadiness(str, Enum):
    """Candidate test case readiness status.

    Unresolved or invalid expectations are marked NOT_READY and excluded
    from scoring. They are never treated as an agent failure.
    """

    READY = "READY"
    NOT_READY = "NOT_READY"


class EvaluationVerdict(str, Enum):
    """Overall component verdict for tool-call correctness (FR-06)."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class CheckStatus(str, Enum):
    """Individual atomic check status."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_EVALUATED = "NOT_EVALUATED"
    UNKNOWN = "UNKNOWN"


class CheckType(str, Enum):
    """Categories of tool-call correctness checks (FR-05)."""

    TOOL_SELECTION = "TOOL_SELECTION"
    ARGUMENT_PRESENCE = "ARGUMENT_PRESENCE"
    ARGUMENT_TYPE = "ARGUMENT_TYPE"
    ARGUMENT_VALUE = "ARGUMENT_VALUE"
    TASK_CONSTRAINT = "TASK_CONSTRAINT"
    ARGUMENT_SOURCE_RELATION = "ARGUMENT_SOURCE_RELATION"


class DiagnosisClassification(str, Enum):
    """Defect localization and diagnosis classification (FR-08)."""

    SUPPORTED_CODE_DEFECT = "SUPPORTED_CODE_DEFECT"
    AGENT_BEHAVIOUR = "AGENT_BEHAVIOUR"
    SPECIFICATION_PROBLEM = "SPECIFICATION_PROBLEM"
    UNKNOWN = "UNKNOWN"


class SourceRelationStatus(str, Enum):
    """Evidence origin relationship status (FR-05/FR-08)."""

    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"

"""C1 Tool-Call Correctness Component Contracts.

Phase 1 contracts defining project inputs, tool definitions, candidate test cases,
runtime traces/evidence, and evaluation/diagnosis structures.
"""

from .base import (
    CaseReadiness,
    CheckStatus,
    CheckType,
    DiagnosisClassification,
    EvaluationVerdict,
    ExecutionStatus,
    ExplicitNull,
    ExplicitNullType,
    SourceRelationStatus,
)
from .candidate_case import (
    CandidateTestCase,
    ConstraintOperator,
    ConstraintType,
    ExpectedCallConstraint,
    ValueConstraint,
)
from .evaluation import (
    CheckOutcome,
    DiagnosisResult,
    EvaluationResult,
    ReasonCode,
)
from .evidence import (
    ExecutionTrace,
    ObservedToolCall,
    RuntimeEvidence,
)
from .project_input import (
    ProjectInput,
    RequirementDefinition,
    ToolCodeMappingReference,
)
from .tool_definition import ToolDefinition

__all__ = [
    "CaseReadiness",
    "CheckOutcome",
    "CheckStatus",
    "CheckType",
    "CandidateTestCase",
    "ConstraintOperator",
    "ConstraintType",
    "DiagnosisClassification",
    "DiagnosisResult",
    "EvaluationResult",
    "EvaluationVerdict",
    "ExecutionStatus",
    "ExecutionTrace",
    "ExpectedCallConstraint",
    "ExplicitNull",
    "ExplicitNullType",
    "ObservedToolCall",
    "ProjectInput",
    "ReasonCode",
    "RequirementDefinition",
    "RuntimeEvidence",
    "SourceRelationStatus",
    "ToolCodeMappingReference",
    "ToolDefinition",
    "ValueConstraint",
]

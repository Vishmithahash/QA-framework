"""Component 1: Explainable Tool-Call Correctness Testing.

Project ID: J26-SE-341
Component Lead / Student: IT23236646
Phase: 1 (Foundation, Contracts, and Validation Services)
"""

from .contracts import (
    CandidateTestCase,
    CaseReadiness,
    CheckOutcome,
    CheckStatus,
    CheckType,
    ConstraintOperator,
    ConstraintType,
    DiagnosisClassification,
    DiagnosisResult,
    EvaluationResult,
    EvaluationVerdict,
    ExecutionStatus,
    ExecutionTrace,
    ExpectedCallConstraint,
    ExplicitNull,
    ExplicitNullType,
    ObservedToolCall,
    ProjectInput,
    ReasonCode,
    RequirementDefinition,
    RuntimeEvidence,
    SourceRelationStatus,
    ToolCodeMappingReference,
    ToolDefinition,
    ValueConstraint,
)
from .services import C1ValidationService

COMPONENT_METADATA = {
    "project_id": "J26-SE-341",
    "component_id": "IT23236646",
    "name": "Explainable Tool-Call Correctness Testing",
    "phase": 1,
    "version": "0.1.0",
    "capabilities": {
        "contracts_and_types": "IMPLEMENTED",
        "input_validation": "IMPLEMENTED",
        "candidate_case_validation": "IMPLEMENTED",
        "status_and_evidence_semantics": "DEFINED",
        "test_generation": "PENDING_PHASE_2",
        "runtime_execution": "PENDING_PHASE_3",
        "correctness_evaluation": "PENDING_PHASE_3",
        "code_diagnosis": "PENDING_PHASE_4",
        "candidate_repair": "PENDING_PHASE_5",
    },
}

__all__ = [
    "COMPONENT_METADATA",
    "C1ValidationService",
    "CandidateTestCase",
    "CaseReadiness",
    "CheckOutcome",
    "CheckStatus",
    "CheckType",
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

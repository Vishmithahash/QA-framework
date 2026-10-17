"""Component 2: State-Aware Multi-Step Workflow Testing.

This component evaluates multi-step tool-using LLM agent workflows against a
validated and versioned Finite State Machine (FSM) or Extended Finite State Machine (EFSM).
It observes ordered agent events and intermediate application state, validates
transitions, guards, invariants, entity continuity, and state effects, and localises
the first workflow-state divergence.
"""

from app.components.c2_state_aware_workflow.contracts import (
    EFSMState,
    EFSMTransition,
    EFSMVariable,
    EvaluationVerdict,
    EvidencePresence,
    GeneratedWorkflowTest,
    LifecycleStatus,
    ModelReadinessInfo,
    ObservedValue,
    PredicateOperator,
    ReasonCode,
    RuntimeEvidenceEvent,
    StructuredPredicate,
    TriState,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
    WorkflowEvaluationResult,
    WorkflowExecutionEvidence,
    WorkflowInput,
    WorkflowModelDefinition,
)
from app.components.c2_state_aware_workflow.models import (
    C2ValidationReport,
    C2WorkflowModel,
)
from app.components.c2_state_aware_workflow.router import router
from app.components.c2_state_aware_workflow.services import (
    ModelBuilderService,
    ModelConstructionResult,
    SafePredicateEngine,
    ScopedExecutionContext,
    WorkflowModelService,
    WorkflowModelValidator,
)

__all__ = [
    "C2ValidationReport",
    "C2WorkflowModel",
    "EFSMState",
    "EFSMTransition",
    "EFSMVariable",
    "EvaluationVerdict",
    "EvidencePresence",
    "GeneratedWorkflowTest",
    "LifecycleStatus",
    "ModelBuilderService",
    "ModelConstructionResult",
    "ModelReadinessInfo",
    "ObservedValue",
    "PredicateOperator",
    "ReasonCode",
    "RuntimeEvidenceEvent",
    "SafePredicateEngine",
    "ScopedExecutionContext",
    "StructuredPredicate",
    "TriState",
    "ValidationIssue",
    "ValidationReport",
    "ValidationSeverity",
    "WorkflowEvaluationResult",
    "WorkflowExecutionEvidence",
    "WorkflowInput",
    "WorkflowModelDefinition",
    "WorkflowModelService",
    "WorkflowModelValidator",
    "router",
]

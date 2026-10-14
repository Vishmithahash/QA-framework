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
    EvaluationVerdict,
    EvidencePresence,
    GeneratedWorkflowTest,
    LifecycleStatus,
    ObservedValue,
    PredicateOperator,
    ReasonCode,
    RuntimeEvidenceEvent,
    StructuredPredicate,
    WorkflowEvaluationResult,
    WorkflowExecutionEvidence,
    WorkflowInput,
    WorkflowModelDefinition,
)
from app.components.c2_state_aware_workflow.models import C2WorkflowModel
from app.components.c2_state_aware_workflow.router import router

__all__ = [
    "C2WorkflowModel",
    "EFSMState",
    "EFSMTransition",
    "EvaluationVerdict",
    "EvidencePresence",
    "GeneratedWorkflowTest",
    "LifecycleStatus",
    "ObservedValue",
    "PredicateOperator",
    "ReasonCode",
    "RuntimeEvidenceEvent",
    "StructuredPredicate",
    "WorkflowEvaluationResult",
    "WorkflowExecutionEvidence",
    "WorkflowInput",
    "WorkflowModelDefinition",
    "router",
]

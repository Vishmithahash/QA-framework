"""Examples package for Component 2."""

from app.components.c2_state_aware_workflow.examples.refund_workflow import (
    demonstrate_refund_lifecycle,
    get_draft_refund_create_request,
    get_draft_refund_workflow_definition,
    get_draft_refund_workflow_input,
)

__all__ = [
    "demonstrate_refund_lifecycle",
    "get_draft_refund_create_request",
    "get_draft_refund_workflow_definition",
    "get_draft_refund_workflow_input",
]

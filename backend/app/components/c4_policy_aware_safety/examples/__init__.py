"""Example domain bindings exports for Component 4 Phase 2."""

from app.components.c4_policy_aware_safety.examples.booking_domain import (
    get_booking_domain_binding,
)
from app.components.c4_policy_aware_safety.examples.refund_domain import (
    get_refund_domain_binding,
)

__all__ = ["get_refund_domain_binding", "get_booking_domain_binding"]

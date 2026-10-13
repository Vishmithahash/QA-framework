"""
FastAPI router for Component 3 (C3):
Robustness and Failure Recovery Testing.

Endpoints:
- GET /api/v1/c3/fault-catalog
- POST /api/v1/c3/cases/validate
"""

from fastapi import APIRouter, status
from app.components.c3_robustness_recovery.schemas import (
    CaseValidationRequest,
    CaseValidationResponse,
    FaultCatalogResponse,
)
from app.components.c3_robustness_recovery.validation import (
    get_operational_fault_catalog,
    validate_candidate_case,
)

router = APIRouter(
    prefix="/api/v1/c3",
    tags=["C3 - Robustness and Failure Recovery"],
)


@router.get(
    "/fault-catalog",
    response_model=FaultCatalogResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve operational fault catalogue",
    description=(
        "Returns the five operational fault families, parameter constraints, and the explicit "
        "indication that fault injection is not implemented in this phase. Catalogue availability "
        "is distinct from adapter support and runtime exposure."
    ),
)
def get_fault_catalog() -> FaultCatalogResponse:
    """Return the static five-family operational fault catalogue."""
    return get_operational_fault_catalog()


@router.post(
    "/cases/validate",
    response_model=CaseValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate candidate fault case statically",
    description=(
        "Performs pure deterministic static validation of candidate case metadata, adapter capabilities, "
        "and recovery contracts. Returns HTTP 200 with STATIC_VALID or TEST_NOT_READY. Malformed request "
        "syntax or invalid schema returns HTTP 422."
    ),
)
def validate_case(request: CaseValidationRequest) -> CaseValidationResponse:
    """Validate declared candidate fault case against adapter capability manifest."""
    return validate_candidate_case(request)

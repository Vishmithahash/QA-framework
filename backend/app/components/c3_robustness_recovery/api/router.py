"""
FastAPI router for Component 3 (C3):
Robustness and Failure Recovery Testing.

Endpoints:
- GET /api/v1/c3/fault-catalog
- POST /api/v1/c3/cases/validate
"""

from fastapi import APIRouter, status
from app.components.c3_robustness_recovery.contracts.generation import (
    CaseGenerationRequest,
    CaseGenerationResponse,
)
from app.components.c3_robustness_recovery.contracts.schemas import (
    CaseValidationRequest,
    CaseValidationResponse,
    FaultCatalogResponse,
)
from app.components.c3_robustness_recovery.services.generation import (
    generate_fault_suite,
)
from app.components.c3_robustness_recovery.services.validation import (
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


@router.post(
    "/cases/generate",
    response_model=CaseGenerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate and freeze candidate fault case suite statically",
    description=(
        "Performs deterministic static candidate generation, static validation, semantic deduplication, "
        "and bounded selection from declared system metadata and capability combinations. Returns HTTP 200 "
        "with selected cases and a content-addressed frozen suite snapshot. Malformed syntax returns HTTP 422. "
        "Does not execute trials, contact external targets, or perform database writes."
    ),
)
def generate_cases(request: CaseGenerationRequest) -> CaseGenerationResponse:
    """Statically generate, deduplicate, select, and freeze a bounded fault test suite."""
    return generate_fault_suite(request)

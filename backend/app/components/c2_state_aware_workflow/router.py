"""FastAPI API routes for Component 2: State-Aware Multi-Step Workflow Testing.

Exposes endpoints for draft workflow model creation, project listing, and versioned retrieval.
Namespace: /api/v1/c2
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.components.c2_state_aware_workflow.contracts.enums import LifecycleStatus
from app.components.c2_state_aware_workflow.schemas.api_models import (
    CreateDraftWorkflowModelRequest,
    WorkflowModelDetailResponse,
    WorkflowModelSummaryResponse,
)
from app.components.c2_state_aware_workflow.services.model_service import (
    ModelNotFoundError,
    ModelVersionAlreadyExistsError,
    WorkflowModelService,
)
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/models",
    response_model=WorkflowModelDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft workflow reference model",
    description="Persists a new behavioral FSM/EFSM reference model. All models created in Phase 1 remain strictly DRAFT.",
)
def create_draft_workflow_model(
    request: CreateDraftWorkflowModelRequest,
    db: Session = Depends(get_db),
) -> WorkflowModelDetailResponse:
    """Creates a new draft workflow model version."""
    service = WorkflowModelService(db)
    try:
        created = service.create_draft_model(request)
        return WorkflowModelDetailResponse.model_validate(created)
    except ModelVersionAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error while creating workflow model")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist workflow model.",
        ) from exc


@router.get(
    "/models",
    response_model=list[WorkflowModelSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="List workflow models for a project",
    description="Retrieves summaries of workflow reference models associated with a specific project.",
)
def list_workflow_models(
    project_id: str = Query(..., description="Project identifier to filter models"),
    domain: str | None = Query(None, description="Optional business domain filter"),
    lifecycle_status: LifecycleStatus | None = Query(
        None,
        description="Optional lifecycle status filter (DRAFT, VALIDATED, APPROVED)",
    ),
    db: Session = Depends(get_db),
) -> list[WorkflowModelSummaryResponse]:
    """Lists workflow model summaries for a given project."""
    service = WorkflowModelService(db)
    models = service.list_models_for_project(
        project_id=project_id,
        domain=domain,
        lifecycle_status=lifecycle_status,
    )
    return [WorkflowModelSummaryResponse.model_validate(m) for m in models]


@router.get(
    "/models/{model_id}/versions/{version}",
    response_model=WorkflowModelDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve a specific workflow model version",
    description="Returns the full detail and structured EFSM definition of a specific model version.",
)
def get_workflow_model_version(
    model_id: str,
    version: str,
    project_id: str | None = Query(
        None, description="Optional project identifier filter"
    ),
    db: Session = Depends(get_db),
) -> WorkflowModelDetailResponse:
    """Retrieves a specific workflow model version by model_id and version."""
    service = WorkflowModelService(db)
    try:
        model_record = service.get_model_version(
            model_id=model_id,
            version=version,
            project_id=project_id,
        )
        return WorkflowModelDetailResponse.model_validate(model_record)
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

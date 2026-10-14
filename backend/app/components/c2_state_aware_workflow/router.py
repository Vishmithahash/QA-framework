"""FastAPI API routes for Component 2: State-Aware Multi-Step Workflow Testing.

Exposes endpoints for candidate model proposal, validation, review/approval,
versioning, project listing, and readiness checking.
Namespace: /api/v1/c2
"""

import logging
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.components.c2_state_aware_workflow.contracts.enums import LifecycleStatus
from app.components.c2_state_aware_workflow.contracts.validation import (
    ModelReadinessInfo,
    ValidationReport,
)
from app.components.c2_state_aware_workflow.schemas.api_models import (
    ApproveWorkflowModelRequest,
    CreateDraftWorkflowModelRequest,
    CreateNewVersionRequest,
    ProposeCandidateModelRequest,
    ProposeCandidateModelResponse,
    ValidateWorkflowModelRequest,
    WorkflowModelDetailResponse,
    WorkflowModelSummaryResponse,
)
from app.components.c2_state_aware_workflow.services.model_builder import (
    ModelBuilderService,
)
from app.components.c2_state_aware_workflow.services.model_service import (
    AmbiguousModelResolutionError,
    ApprovedModelImmutableError,
    ModelNotFoundError,
    ModelValidationFailedError,
    ModelVersionAlreadyExistsError,
    StaleValidationReportError,
    WorkflowModelService,
)
from app.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/models/propose",
    response_model=ProposeCandidateModelResponse,
    status_code=status.HTTP_200_OK,
    summary="Propose a candidate workflow model",
    description=(
        "Synthesizes a candidate behavioral EFSM model from normalized WorkflowInput. "
        "Operates deterministically without requiring paid API credentials."
    ),
)
def propose_candidate_model(
    request: ProposeCandidateModelRequest,
) -> ProposeCandidateModelResponse:
    """Proposes a candidate reference model from structured business rules and tools."""
    builder = ModelBuilderService()
    result = builder.build_candidate_model(
        workflow_input=request.workflow_input,
        model_id=request.model_id,
        version=request.version,
    )
    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Candidate model construction failed due to insufficient input.",
                "diagnostics": result.diagnostics,
            },
        )
    return ProposeCandidateModelResponse(
        success=True,
        candidate_model=result.candidate_model,
        diagnostics=result.diagnostics,
        assumptions=result.assumptions,
        source_rules=result.source_rules,
        builder_provenance=result.builder_provenance,
    )


@router.post(
    "/models",
    response_model=WorkflowModelDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a draft workflow reference model",
    description="Persists a new behavioral FSM/EFSM reference model. All newly created models start strictly as DRAFT.",
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
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
        None, description="Project identifier filter to disambiguate model version"
    ),
    x_project_id: str | None = Header(
        None, alias="X-Project-ID", description="Optional project context header"
    ),
    db: Session = Depends(get_db),
) -> WorkflowModelDetailResponse:
    """Retrieves a specific workflow model version by model_id and version."""
    effective_project = project_id or x_project_id
    service = WorkflowModelService(db)
    try:
        model_record = service.get_model_version(
            model_id=model_id,
            version=version,
            project_id=effective_project,
        )
        return WorkflowModelDetailResponse.model_validate(model_record)
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except AmbiguousModelResolutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/models/{model_id}/versions/{version}/validate",
    response_model=ValidationReport,
    status_code=status.HTTP_200_OK,
    summary="Validate a workflow model version",
    description=(
        "Executes structural and bounded semantic validation. "
        "Successful validation advances model to VALIDATED. "
        "Persists validation evidence with the exact definition content hash."
    ),
)
def validate_workflow_model(
    model_id: str,
    version: str,
    request: ValidateWorkflowModelRequest,
    db: Session = Depends(get_db),
) -> ValidationReport:
    """Validates the reference model and persists the resulting evidence report."""
    service = WorkflowModelService(db)
    try:
        _record, _val_row, report = service.validate_model_version(
            project_id=request.project_id,
            model_id=model_id,
            version=version,
            config=request.config,
        )
        return report
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ApprovedModelImmutableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/models/{model_id}/versions/{version}/validation",
    response_model=ValidationReport,
    status_code=status.HTTP_200_OK,
    summary="Retrieve validation report for a model version",
    description="Returns the latest persisted validation report associated with the model version.",
)
def get_model_validation_report(
    model_id: str,
    version: str,
    project_id: str = Query(..., description="Project identifier"),
    db: Session = Depends(get_db),
) -> ValidationReport:
    """Retrieves the latest persisted validation report."""
    service = WorkflowModelService(db)
    val_record = service.get_latest_validation_report(
        project_id=project_id,
        model_id=model_id,
        version=version,
    )
    if val_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No validation report found for model '{model_id}' version '{version}' in project '{project_id}'.",
        )
    return ValidationReport.model_validate(val_record.report)


@router.post(
    "/models/{model_id}/versions/{version}/approve",
    response_model=WorkflowModelDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve a validated workflow model version",
    description=(
        "Records explicit domain review and transitions model to APPROVED. "
        "Requires current valid validation matching the exact definition content hash. "
        "Freezes the definition and guarantees immutability."
    ),
)
def approve_workflow_model_version(
    model_id: str,
    version: str,
    request: ApproveWorkflowModelRequest,
    db: Session = Depends(get_db),
) -> WorkflowModelDetailResponse:
    """Records domain review decision and approves the model version."""
    service = WorkflowModelService(db)
    try:
        approved_record = service.approve_model_version(
            project_id=request.project_id,
            model_id=model_id,
            version=version,
            reviewer=request.reviewer,
            review_basis=request.review_basis,
            review_notes=request.review_notes,
            is_development_review=request.is_development_review,
            confirm_definition_hash=request.confirm_definition_hash,
        )
        return WorkflowModelDetailResponse.model_validate(approved_record)
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ApprovedModelImmutableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except StaleValidationReportError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except ModelValidationFailedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc


@router.post(
    "/models/{model_id}/versions",
    response_model=WorkflowModelDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new draft version of a model",
    description="Creates a new version of an existing model. The new version starts strictly in DRAFT.",
)
def create_new_model_version(
    model_id: str,
    request: CreateNewVersionRequest,
    db: Session = Depends(get_db),
) -> WorkflowModelDetailResponse:
    """Creates a new draft version for a workflow model."""
    service = WorkflowModelService(db)
    try:
        new_record = service.create_new_draft_version(
            project_id=request.project_id,
            model_id=model_id,
            new_version=request.version,
            definition=request.definition,
            domain=request.domain,
            name=request.name,
            description=request.description,
        )
        return WorkflowModelDetailResponse.model_validate(new_record)
    except ModelVersionAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/models/{model_id}/versions/{version}/readiness",
    response_model=ModelReadinessInfo,
    status_code=status.HTTP_200_OK,
    summary="Check workflow model readiness",
    description=(
        "Verifies whether the reference model is ready for test generation and runtime alignment. "
        "Returns MODEL NOT READY if unapproved, invalid, or contradictory."
    ),
)
def check_model_readiness(
    model_id: str,
    version: str,
    project_id: str = Query(..., description="Project identifier"),
    db: Session = Depends(get_db),
) -> ModelReadinessInfo:
    """Evaluates readiness status of the model version."""
    service = WorkflowModelService(db)
    try:
        return service.check_model_readiness(
            project_id=project_id,
            model_id=model_id,
            version=version,
        )
    except ModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

"""FastAPI router for C4 Policy-Aware Safety and Prompt-Injection Testing."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.components.c4_policy_aware_safety.acceptance.contract_service import (
    ContractAcceptanceService,
)
from app.components.c4_policy_aware_safety.api.schemas import (
    AcceptContractRequest,
    CreateContractRequest,
    DeriveCandidateRulesRequest,
    DeriveCandidateRulesResponse,
    EvaluateContractRequest,
    RegisterJsonArtifactRequest,
    RegisterTextArtifactRequest,
)
from app.components.c4_policy_aware_safety.contracts.artifacts import ArtifactVersion
from app.components.c4_policy_aware_safety.contracts.findings import (
    C4EvaluationReport,
    EvaluationFinding,
)
from app.components.c4_policy_aware_safety.contracts.policy import (
    ContractLifecycleStatus,
    PolicyContract,
)
from app.components.c4_policy_aware_safety.derivation.extractor import (
    ControlledLanguageExtractor,
    StructuredPolicyImporter,
)
from app.components.c4_policy_aware_safety.evaluation.evaluator import (
    DeterministicPolicyEvaluator,
)
from app.components.c4_policy_aware_safety.intake.artifact_service import (
    ArtifactIntakeService,
)
from app.components.c4_policy_aware_safety.persistence.repository import C4Repository
from app.components.c4_policy_aware_safety.validation.policy_validator import (
    PolicyContractValidator,
)
from app.database import get_db

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/c4", tags=["C4 Policy-Aware Safety"]
)

intake_service = ArtifactIntakeService()
evaluator = DeterministicPolicyEvaluator()


# --- Artifact Intake ---


@router.post(
    "/artifacts/text",
    response_model=ArtifactVersion,
    status_code=status.HTTP_201_CREATED,
)
def register_text_artifact(
    project_id: str,
    payload: RegisterTextArtifactRequest,
    db: Session = Depends(get_db),
) -> ArtifactVersion:
    """Register a text artifact with section offsets."""
    try:
        artifact = intake_service.register_text_artifact(
            project_id=project_id,
            artifact_id=payload.artifact_id,
            version=payload.version,
            kind=payload.kind,
            raw_text=payload.content,
            sections=payload.sections,
            metadata=payload.metadata,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e

    repo = C4Repository(db)
    repo.save_artifact(artifact)
    return artifact


@router.post(
    "/artifacts/json",
    response_model=ArtifactVersion,
    status_code=status.HTTP_201_CREATED,
)
def register_json_artifact(
    project_id: str,
    payload: RegisterJsonArtifactRequest,
    db: Session = Depends(get_db),
) -> ArtifactVersion:
    """Register a structured JSON policy artifact."""
    artifact = intake_service.register_json_artifact(
        project_id=project_id,
        artifact_id=payload.artifact_id,
        version=payload.version,
        kind=payload.kind,
        json_data=payload.json_data,
        metadata=payload.metadata,
    )
    repo = C4Repository(db)
    repo.save_artifact(artifact)
    return artifact


@router.get(
    "/artifacts/{artifact_id}/versions/{version}", response_model=ArtifactVersion
)
def get_artifact_version(
    project_id: str,
    artifact_id: str,
    version: str,
    db: Session = Depends(get_db),
) -> ArtifactVersion:
    """Retrieve an artifact version."""
    repo = C4Repository(db)
    artifact = repo.get_artifact(project_id, artifact_id, version)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{artifact_id}' (v{version}) not found in project '{project_id}'.",
        )
    return artifact


@router.get("/artifacts", response_model=list[ArtifactVersion])
def list_artifacts(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[ArtifactVersion]:
    """List all artifacts registered for this project."""
    repo = C4Repository(db)
    return repo.list_artifacts(project_id)


# --- Candidate Rule Derivation ---


@router.post("/derive-candidate-rules", response_model=DeriveCandidateRulesResponse)
def derive_candidate_rules(
    project_id: str,
    payload: DeriveCandidateRulesRequest,
    db: Session = Depends(get_db),
) -> DeriveCandidateRulesResponse:
    """Derive candidate policy rules from an intake artifact."""
    repo = C4Repository(db)
    artifact = repo.get_artifact(
        project_id, payload.artifact_id, payload.artifact_version
    )
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact '{payload.artifact_id}' (v{payload.artifact_version}) not found in project '{project_id}'.",
        )

    if payload.extraction_method == "structured_json":
        importer = StructuredPolicyImporter()
        try:
            rules = importer.extract_candidates(artifact)
            issues = []
        except ValueError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
            ) from err
    elif payload.extraction_method == "controlled_language":
        extractor = ControlledLanguageExtractor()
        rules, issues = extractor.extract_candidates_with_issues(artifact)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported extraction method '{payload.extraction_method}'.",
        )

    return DeriveCandidateRulesResponse(candidate_rules=rules, validation_issues=issues)


# --- Policy Contracts ---


@router.post(
    "/contracts", response_model=PolicyContract, status_code=status.HTTP_201_CREATED
)
def create_policy_contract(
    project_id: str,
    payload: CreateContractRequest,
    db: Session = Depends(get_db),
) -> PolicyContract:
    """Create a new policy contract draft."""
    contract = PolicyContract(
        contract_id=payload.contract_id,
        project_id=project_id,
        version=payload.version,
        lifecycle_status=ContractLifecycleStatus.DRAFT,
        rules=payload.rules,
        referenced_artifact_versions=payload.referenced_artifact_versions,
    )
    contract.content_hash = contract.compute_content_hash()

    repo = C4Repository(db)
    repo.save_contract(contract)
    return contract


@router.get(
    "/contracts/{contract_id}/versions/{version}", response_model=PolicyContract
)
def get_policy_contract(
    project_id: str,
    contract_id: str,
    version: int,
    db: Session = Depends(get_db),
) -> PolicyContract:
    """Retrieve a specific policy contract version."""
    repo = C4Repository(db)
    contract = repo.get_contract(project_id, contract_id, version)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy contract '{contract_id}' (v{version}) not found in project '{project_id}'.",
        )
    return contract


@router.post(
    "/contracts/{contract_id}/versions/{version}/validate",
    response_model=PolicyContract,
)
def validate_policy_contract(
    project_id: str,
    contract_id: str,
    version: int,
    db: Session = Depends(get_db),
) -> PolicyContract:
    """Validate a policy contract draft against project artifacts."""
    repo = C4Repository(db)
    contract = repo.get_contract(project_id, contract_id, version)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy contract '{contract_id}' (v{version}) not found.",
        )

    # Load all project artifacts into validator
    artifacts = repo.list_artifacts(project_id)
    artifacts_map = {(a.project_id, a.artifact_id, a.version): a for a in artifacts}
    validator = PolicyContractValidator(artifacts_map)

    validated_contract = validator.validate_contract(contract)
    repo.save_contract(validated_contract)
    return validated_contract


@router.post(
    "/contracts/{contract_id}/versions/{version}/accept", response_model=PolicyContract
)
def accept_policy_contract(
    project_id: str,
    contract_id: str,
    version: int,
    payload: AcceptContractRequest,
    db: Session = Depends(get_db),
) -> PolicyContract:
    """Explicitly accept a validated policy contract."""
    repo = C4Repository(db)
    contract = repo.get_contract(project_id, contract_id, version)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy contract '{contract_id}' (v{version}) not found.",
        )

    try:
        accepted_contract = ContractAcceptanceService.accept_contract(
            contract=contract,
            accepted_by=payload.accepted_by,
            justification=payload.justification,
            extra_metadata=payload.metadata,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err

    repo.save_contract(accepted_contract)
    return accepted_contract


# --- Evaluation ---


@router.post(
    "/contracts/{contract_id}/versions/{version}/evaluate",
    response_model=C4EvaluationReport,
)
def evaluate_policy_contract(
    project_id: str,
    contract_id: str,
    version: int,
    payload: EvaluateContractRequest,
    db: Session = Depends(get_db),
) -> C4EvaluationReport:
    """
    Evaluate an accepted policy contract against supplied evidence payload.
    Rejects evaluation if contract is not in ACCEPTED status.
    """
    if payload.evidence.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Evidence project_id '{payload.evidence.project_id}' does not match route project_id '{project_id}'.",
        )

    repo = C4Repository(db)
    contract = repo.get_contract(project_id, contract_id, version)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy contract '{contract_id}' (v{version}) not found.",
        )

    if contract.lifecycle_status != ContractLifecycleStatus.ACCEPTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Contract '{contract_id}' (v{version}) is in '{contract.lifecycle_status}' status. "
                "Only ACCEPTED contracts can be evaluated against evidence."
            ),
        )

    report = evaluator.evaluate_contract(
        contract=contract,
        evidence=payload.evidence,
        benign_task_completed=payload.benign_task_completed,
    )

    # Persist findings
    repo.save_findings(report.findings)
    return report


# --- Findings Query ---


@router.get("/findings", response_model=list[EvaluationFinding])
def get_findings(
    project_id: str,
    case_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[EvaluationFinding]:
    """Retrieve stored evaluation findings filtered by project, case, and run."""
    repo = C4Repository(db)
    return repo.get_findings(project_id, case_id=case_id, run_id=run_id)

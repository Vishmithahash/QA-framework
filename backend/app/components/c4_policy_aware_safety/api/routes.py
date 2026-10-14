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
    FreezeBatchResponse,
    GenerateTestBatchRequest,
    GenerateTestBatchResponse,
    RegisterDomainBindingRequest,
    RegisterJsonArtifactRequest,
    RegisterTextArtifactRequest,
)
from app.components.c4_policy_aware_safety.contracts.artifacts import ArtifactVersion
from app.components.c4_policy_aware_safety.contracts.domain_binding import DomainBinding
from app.components.c4_policy_aware_safety.contracts.evidence import EvidenceOrigin
from app.components.c4_policy_aware_safety.contracts.findings import (
    C4EvaluationReport,
    EvaluationFinding,
)
from app.components.c4_policy_aware_safety.contracts.policy import (
    ContractLifecycleStatus,
    PolicyContract,
)
from app.components.c4_policy_aware_safety.contracts.test_cases import (
    AgentFacingPayload,
    EvaluatorOnlyBundle,
    GeneratedTestCase,
)
from app.components.c4_policy_aware_safety.derivation.extractor import (
    ControlledLanguageExtractor,
    StructuredPolicyImporter,
)
from app.components.c4_policy_aware_safety.evaluation.evaluator import (
    DeterministicPolicyEvaluator,
)
from app.components.c4_policy_aware_safety.generation.generator import (
    DeterministicTestGenerator,
)
from app.components.c4_policy_aware_safety.generation.report import (
    C4GenerationBatchReport,
)
from app.components.c4_policy_aware_safety.intake.artifact_service import (
    ArtifactIntakeService,
)
from app.components.c4_policy_aware_safety.persistence.repository import C4Repository
from app.components.c4_policy_aware_safety.validation.case_validator import (
    GeneratedCaseValidator,
)
from app.components.c4_policy_aware_safety.validation.policy_validator import (
    PolicyContractValidator,
)
from app.database import get_db

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/c4", tags=["C4 Policy-Aware Safety"]
)

intake_service = ArtifactIntakeService()
evaluator = DeterministicPolicyEvaluator()
test_generator = DeterministicTestGenerator()
case_validator = GeneratedCaseValidator()


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
    repo = C4Repository(db)
    existing = repo.get_contract(project_id, payload.contract_id, payload.version)
    if existing and existing.lifecycle_status == ContractLifecycleStatus.ACCEPTED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot overwrite accepted policy contract '{payload.contract_id}' (v{payload.version}). Accepted contracts are immutable.",
        )

    contract = PolicyContract(
        contract_id=payload.contract_id,
        project_id=project_id,
        version=payload.version,
        lifecycle_status=ContractLifecycleStatus.DRAFT,
        rules=payload.rules,
        referenced_artifact_versions=payload.referenced_artifact_versions,
    )
    contract.content_hash = contract.compute_content_hash()

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

    # Preserve explicit synthetic/development boundary: caller-supplied unauthenticated
    # evidence cannot self-attest to verified harness/application evidence
    if payload.evidence.origin != EvidenceOrigin.SYNTHETIC_DEVELOPER_FIXTURE:
        payload.evidence.origin = EvidenceOrigin.SYNTHETIC_DEVELOPER_FIXTURE

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


# --- Domain Bindings (Phase 2) ---


@router.post(
    "/domain-bindings",
    response_model=DomainBinding,
    status_code=status.HTTP_201_CREATED,
)
def register_domain_binding(
    project_id: str,
    payload: RegisterDomainBindingRequest,
    db: Session = Depends(get_db),
) -> DomainBinding:
    """Register domain binding facts and capabilities."""
    binding = DomainBinding(
        project_id=project_id,
        domain_id=payload.domain_id,
        binding_version=payload.binding_version,
        description=payload.description,
        roles=payload.roles,
        tools=payload.tools,
        resources=payload.resources,
        field_types=payload.field_types,
        approval_states=payload.approval_states,
        synthetic_fixtures=payload.synthetic_fixtures,
        protected_data=payload.protected_data,
        untrusted_sources=payload.untrusted_sources,
        declared_capabilities=payload.declared_capabilities,
        metadata=payload.metadata,
    )
    repo = C4Repository(db)
    repo.save_domain_binding(binding)
    return binding


@router.get(
    "/domain-bindings/{domain_id}/versions/{version}",
    response_model=DomainBinding,
)
def get_domain_binding(
    project_id: str,
    domain_id: str,
    version: str,
    db: Session = Depends(get_db),
) -> DomainBinding:
    """Retrieve a specific domain binding version."""
    repo = C4Repository(db)
    binding = repo.get_domain_binding(project_id, domain_id, version)
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Domain binding '{domain_id}' (v{version}) not found in project '{project_id}'.",
        )
    return binding


@router.get("/domain-bindings", response_model=list[DomainBinding])
def list_domain_bindings(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[DomainBinding]:
    """List all domain bindings registered for this project."""
    repo = C4Repository(db)
    return repo.list_domain_bindings(project_id)


# --- Automated Test Generation (Phase 2) ---


@router.post(
    "/test-generation/generate",
    response_model=GenerateTestBatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def generate_test_cases(
    project_id: str,
    payload: GenerateTestBatchRequest,
    db: Session = Depends(get_db),
) -> GenerateTestBatchResponse:
    """
    Generate policy-specific benign and adversarial test cases offline.
    Requires accepted contract and registered domain binding.
    """
    repo = C4Repository(db)
    contract = repo.get_contract(
        project_id, payload.contract_id, payload.contract_version
    )
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy contract '{payload.contract_id}' (v{payload.contract_version}) not found.",
        )

    if contract.lifecycle_status != ContractLifecycleStatus.ACCEPTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Contract '{contract.contract_id}' (v{contract.version}) is in '{contract.lifecycle_status}' status. "
                "Only ACCEPTED contracts can be used for test generation."
            ),
        )

    domain_binding = repo.get_domain_binding(
        project_id, payload.domain_id, payload.domain_binding_version
    )
    if not domain_binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Domain binding '{payload.domain_id}' (v{payload.domain_binding_version}) not found.",
        )

    cases, report = test_generator.generate_batch(
        contract=contract,
        domain_binding=domain_binding,
        seed=payload.seed,
        categories=payload.categories,
        num_cases_per_rule=payload.num_cases_per_rule,
    )

    # Independent static validation of generated cases
    validated_cases = case_validator.validate_batch(cases, contract, domain_binding)

    # Persist batch and cases
    repo.save_generation_batch(report)
    for c in validated_cases:
        repo.save_test_case(c)

    return GenerateTestBatchResponse(
        batch_id=report.batch_id,
        report=report,
        generated_cases=validated_cases,
    )


@router.get(
    "/test-generation/batches/{batch_id}",
    response_model=C4GenerationBatchReport,
)
def get_generation_batch_report(
    project_id: str,
    batch_id: str,
    db: Session = Depends(get_db),
) -> C4GenerationBatchReport:
    """Retrieve generation batch report."""
    repo = C4Repository(db)
    report = repo.get_generation_batch(project_id, batch_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Generation batch '{batch_id}' not found in project '{project_id}'.",
        )
    return report


@router.get("/test-cases", response_model=list[GeneratedTestCase])
def list_test_cases(
    project_id: str,
    batch_id: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
) -> list[GeneratedTestCase]:
    """List generated test cases matching filters."""
    repo = C4Repository(db)
    return repo.list_test_cases(
        project_id, batch_id=batch_id, category=category, status=status_filter
    )


@router.get(
    "/test-cases/{case_id}/versions/{version}",
    response_model=GeneratedTestCase,
)
def get_test_case(
    project_id: str,
    case_id: str,
    version: int,
    db: Session = Depends(get_db),
) -> GeneratedTestCase:
    """Retrieve a specific test case version."""
    repo = C4Repository(db)
    case = repo.get_test_case(project_id, case_id, version)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case '{case_id}' (v{version}) not found in project '{project_id}'.",
        )
    return case


@router.post(
    "/test-cases/{case_id}/versions/{version}/validate",
    response_model=GeneratedTestCase,
)
def validate_test_case(
    project_id: str,
    case_id: str,
    version: int,
    db: Session = Depends(get_db),
) -> GeneratedTestCase:
    """Independently validate a generated test case."""
    repo = C4Repository(db)
    case = repo.get_test_case(project_id, case_id, version)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case '{case_id}' (v{version}) not found.",
        )

    contract = repo.get_contract(project_id, case.contract_id, case.contract_version)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target contract '{case.contract_id}' (v{case.contract_version}) not found.",
        )

    domain_binding = repo.get_domain_binding(
        project_id, case.domain_id, case.domain_binding_version
    )
    if not domain_binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Domain binding '{case.domain_id}' (v{case.domain_binding_version}) not found.",
        )

    validated = case_validator.validate_case(case, contract, domain_binding)
    repo.save_test_case(validated)
    return validated


@router.post(
    "/test-cases/{case_id}/versions/{version}/freeze",
    response_model=GeneratedTestCase,
)
def freeze_test_case(
    project_id: str,
    case_id: str,
    version: int,
    db: Session = Depends(get_db),
) -> GeneratedTestCase:
    """Explicitly freeze a validated test case, making it immutable."""
    repo = C4Repository(db)
    try:
        frozen = repo.freeze_test_case(project_id, case_id, version)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err
    return frozen


@router.post(
    "/test-generation/batches/{batch_id}/freeze",
    response_model=FreezeBatchResponse,
)
def freeze_generation_batch(
    project_id: str,
    batch_id: str,
    db: Session = Depends(get_db),
) -> FreezeBatchResponse:
    """Freeze all validated test cases in a generation batch."""
    repo = C4Repository(db)
    try:
        frozen_cases = repo.freeze_batch(project_id, batch_id)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err

    return FreezeBatchResponse(
        batch_id=batch_id,
        total_frozen=len(frozen_cases),
        frozen_cases=frozen_cases,
    )


@router.get(
    "/test-cases/{case_id}/versions/{version}/export/agent-payload",
    response_model=AgentFacingPayload,
)
def export_agent_facing_payload(
    project_id: str,
    case_id: str,
    version: int,
    db: Session = Depends(get_db),
) -> AgentFacingPayload:
    """Export strictly agent-facing payload, omitting all evaluator-only assertions and objectives."""
    repo = C4Repository(db)
    case = repo.get_test_case(project_id, case_id, version)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case '{case_id}' (v{version}) not found.",
        )
    return case.build_agent_facing_payload()


@router.get(
    "/test-cases/{case_id}/versions/{version}/export/evaluator-bundle",
    response_model=EvaluatorOnlyBundle,
)
def export_evaluator_bundle(
    project_id: str,
    case_id: str,
    version: int,
    db: Session = Depends(get_db),
) -> EvaluatorOnlyBundle:
    """Export evaluator-only bundle containing hidden expectations and attacker objectives."""
    repo = C4Repository(db)
    case = repo.get_test_case(project_id, case_id, version)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Test case '{case_id}' (v{version}) not found.",
        )
    return case.build_evaluator_bundle()

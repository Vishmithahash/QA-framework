"""Service layer for C2 workflow model management, validation, and lifecycle persistence."""

from datetime import datetime, timezone
import hashlib
import json
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.components.c2_state_aware_workflow.contracts.efsm import (
    WorkflowModelDefinition,
)
from app.components.c2_state_aware_workflow.contracts.enums import (
    EvaluationVerdict,
    LifecycleStatus,
    ReasonCode,
)
from app.components.c2_state_aware_workflow.contracts.validation import (
    ModelReadinessInfo,
    ValidationReport,
)
from app.components.c2_state_aware_workflow.models.workflow_model import (
    C2ValidationReport,
    C2WorkflowModel,
)
from app.components.c2_state_aware_workflow.schemas.api_models import (
    CreateDraftWorkflowModelRequest,
)

# Audit, timestamp, and lifecycle fields strictly excluded from content hashing
EXCLUDED_METADATA_FIELDS = {
    "id",
    "created_at",
    "updated_at",
    "lifecycle_status",
    "content_hash",
    "review_notes",
    "review_basis",
    "reviewed_by",
    "reviewed_at",
    "approved_by",
    "approved_at",
}


class C2ModelServiceError(Exception):
    """Base exception for C2 model service operations."""


class ModelVersionAlreadyExistsError(C2ModelServiceError):
    """Raised when attempting to create a model version that already exists."""


class ModelNotFoundError(C2ModelServiceError):
    """Raised when a requested model version cannot be found."""


class AmbiguousModelResolutionError(C2ModelServiceError):
    """Raised when model retrieval is ambiguous across multiple projects."""


class ApprovedModelImmutableError(C2ModelServiceError):
    """Raised when attempting to modify an approved reference model version."""


class ModelValidationFailedError(C2ModelServiceError):
    """Raised when a model fails required validation or contains blocking issues."""


class StaleValidationReportError(C2ModelServiceError):
    """Raised when attempting approval using a stale validation report."""


class InvalidLifecycleTransitionError(C2ModelServiceError):
    """Raised when an illegal lifecycle transition is attempted."""


def compute_canonical_content_hash(
    definition: dict[str, Any] | WorkflowModelDefinition,
) -> str:
    """Computes a deterministic SHA-256 hash from canonical JSON representation.

    Excludes timestamps, lifecycle status, review/approval audit metadata, and database IDs.
    Keys are strictly sorted with uniform compact separators to guarantee hash stability
    across environments and serialization runs.
    """
    if isinstance(definition, WorkflowModelDefinition):
        raw_dict = definition.model_dump(mode="json")
    elif isinstance(definition, dict):
        raw_dict = definition
    else:
        raise ValueError("Definition must be a dictionary or WorkflowModelDefinition.")

    # Strip lifecycle and audit metadata to preserve immutable hash across status changes
    clean_dict = {
        k: v for k, v in raw_dict.items() if k not in EXCLUDED_METADATA_FIELDS
    }

    canonical_json = json.dumps(clean_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class WorkflowModelService:
    """Encapsulates database operations, validation persistence, and lifecycle transitions."""

    def __init__(self, db: Session):
        self.db = db

    def create_draft_model(
        self, request: CreateDraftWorkflowModelRequest
    ) -> C2WorkflowModel:
        """Persists a new workflow model in DRAFT lifecycle state.

        Enforces:
        1. All newly created models start strictly as DRAFT.
        2. Unique constraint on (project_id, model_id, version).
        3. Deterministic canonical content hashing.
        """
        def_obj = request.definition
        model_id = def_obj.model_id
        version = def_obj.version

        # Verify project_id consistency
        if def_obj.project_id and def_obj.project_id != request.project_id:
            raise ValueError(
                f"Project ID mismatch: request specifies '{request.project_id}', "
                f"but definition contains '{def_obj.project_id}'."
            )

        # Check existing version under exact (project_id, model_id, version)
        existing = self.db.execute(
            select(C2WorkflowModel).where(
                C2WorkflowModel.project_id == request.project_id,
                C2WorkflowModel.model_id == model_id,
                C2WorkflowModel.version == version,
            )
        ).scalar_one_or_none()

        if existing is not None:
            raise ModelVersionAlreadyExistsError(
                f"Model '{model_id}' version '{version}' already exists in project '{request.project_id}'."
            )

        definition_dict = def_obj.model_dump(mode="json")
        content_hash = compute_canonical_content_hash(definition_dict)

        model_record = C2WorkflowModel(
            model_id=model_id,
            version=version,
            schema_version=def_obj.schema_version,
            project_id=request.project_id,
            domain=request.domain,
            name=request.name,
            description=request.description,
            definition=definition_dict,
            content_hash=content_hash,
            lifecycle_status=LifecycleStatus.DRAFT.value,
        )

        self.db.add(model_record)
        self.db.commit()
        self.db.refresh(model_record)
        return model_record

    def list_models_for_project(
        self,
        project_id: str,
        domain: str | None = None,
        lifecycle_status: LifecycleStatus | None = None,
    ) -> list[C2WorkflowModel]:
        """Lists workflow models for a given project with optional filters."""
        stmt = select(C2WorkflowModel).where(C2WorkflowModel.project_id == project_id)

        if domain:
            stmt = stmt.where(C2WorkflowModel.domain == domain)
        if lifecycle_status:
            stmt = stmt.where(
                C2WorkflowModel.lifecycle_status == lifecycle_status.value
            )

        stmt = stmt.order_by(C2WorkflowModel.created_at.desc())
        return list(self.db.execute(stmt).scalars().all())

    def get_model_version(
        self,
        model_id: str,
        version: str,
        project_id: str | None = None,
    ) -> C2WorkflowModel:
        """Retrieves a specific workflow model version.

        Guarantees:
        - If project_id is provided, filters strictly by (project_id, model_id, version).
        - If project_id is omitted and multiple projects contain (model_id, version),
          raises AmbiguousModelResolutionError to prevent cross-project data leakage.
        """
        stmt = select(C2WorkflowModel).where(
            C2WorkflowModel.model_id == model_id,
            C2WorkflowModel.version == version,
        )
        if project_id:
            stmt = stmt.where(C2WorkflowModel.project_id == project_id)

        records = list(self.db.execute(stmt).scalars().all())
        if not records:
            project_hint = f" in project '{project_id}'" if project_id else ""
            raise ModelNotFoundError(
                f"Workflow model '{model_id}' version '{version}' not found{project_hint}."
            )

        if len(records) > 1:
            raise AmbiguousModelResolutionError(
                f"Ambiguous model retrieval: multiple projects contain model '{model_id}' version '{version}'. "
                "Specify verified project_id to disambiguate."
            )

        return records[0]

    def validate_model_version(
        self,
        project_id: str,
        model_id: str,
        version: str,
        config: dict[str, Any] | None = None,
    ) -> tuple[C2WorkflowModel, C2ValidationReport, ValidationReport]:
        """Runs the reference-model validator, persists the evidence report, and updates lifecycle.

        Rules:
        - Successful required validation allows transition from DRAFT to VALIDATED.
        - Validation failure prevents progression and records the reasons; model remains DRAFT.
        - Persists validation evidence associated with the exact model version and definition hash.
        - Transactional.
        """
        model_record = self.get_model_version(model_id, version, project_id=project_id)
        self.assert_version_mutable(model_record)

        # Lazy import to avoid circular dependency
        from app.components.c2_state_aware_workflow.services.model_validator import (
            WorkflowModelValidator,
        )

        model_def = WorkflowModelDefinition.model_validate(model_record.definition)
        current_hash = compute_canonical_content_hash(model_def)

        # Execute structural and bounded semantic checks
        validator = WorkflowModelValidator()
        report = validator.validate(model_def, config=config)

        # Persist validation evidence in c2_validation_reports
        val_record = C2ValidationReport(
            project_id=project_id,
            model_id=model_id,
            version=version,
            definition_hash=current_hash,
            validator_version=report.validator_version,
            is_valid=report.is_valid,
            has_blocking_issues=report.has_blocking_issues,
            report=report.model_dump(mode="json"),
        )
        self.db.add(val_record)

        # Lifecycle update: DRAFT -> VALIDATED only if validation succeeded without blocking issues
        if report.is_valid and not report.has_blocking_issues:
            if model_record.lifecycle_status == LifecycleStatus.DRAFT.value:
                model_record.lifecycle_status = LifecycleStatus.VALIDATED.value
                model_record.updated_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(model_record)
        self.db.refresh(val_record)
        return model_record, val_record, report

    def get_latest_validation_report(
        self,
        project_id: str,
        model_id: str,
        version: str,
    ) -> C2ValidationReport | None:
        """Retrieves the most recent persisted validation report for a model version."""
        stmt = (
            select(C2ValidationReport)
            .where(
                C2ValidationReport.project_id == project_id,
                C2ValidationReport.model_id == model_id,
                C2ValidationReport.version == version,
            )
            .order_by(C2ValidationReport.created_at.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def approve_model_version(
        self,
        project_id: str,
        model_id: str,
        version: str,
        reviewer: str,
        review_basis: str,
        review_notes: str | None = None,
        is_development_review: bool = True,
        confirm_definition_hash: str | None = None,
    ) -> C2WorkflowModel:
        """Transitions a VALIDATED model version to APPROVED.

        Rules:
        - Structural validation alone must never produce APPROVED.
        - APPROVED requires successful current validation plus an explicit domain-review decision.
        - Definition hash must match current validation report hash (rejects stale validation).
        - Freezes the definition and records reviewer identity, review basis, notes, and timestamp.
        - Preserves the immutable definition hash.
        - Transactional.
        """
        model_record = self.get_model_version(model_id, version, project_id=project_id)

        if model_record.lifecycle_status == LifecycleStatus.APPROVED.value:
            raise ApprovedModelImmutableError(
                f"Model '{model_id}' version '{version}' is already APPROVED and immutable."
            )

        # Retrieve latest validation report
        latest_val = self.get_latest_validation_report(project_id, model_id, version)
        if latest_val is None:
            raise ModelValidationFailedError(
                f"Model '{model_id}' version '{version}' has not been validated. "
                "Validation is mandatory prior to approval."
            )

        # Check for stale validation: definition hash must match exact current model hash
        if latest_val.definition_hash != model_record.content_hash:
            raise StaleValidationReportError(
                f"Validation report definition hash '{latest_val.definition_hash}' does not match "
                f"current model content hash '{model_record.content_hash}'. Re-validation is required."
            )

        if (
            confirm_definition_hash
            and confirm_definition_hash != model_record.content_hash
        ):
            raise StaleValidationReportError(
                f"Confirmation hash '{confirm_definition_hash}' does not match model content hash '{model_record.content_hash}'."
            )

        if not latest_val.is_valid or latest_val.has_blocking_issues:
            raise ModelValidationFailedError(
                f"Cannot approve model '{model_id}' version '{version}': "
                "Validation report contains unresolved blocking issues."
            )

        # Format reviewer attribution
        reviewer_label = reviewer.strip()
        if is_development_review and not reviewer_label.startswith("[DEV_REVIEW]"):
            reviewer_label = f"[DEV_REVIEW] {reviewer_label}"

        # Transactional freeze and approval
        model_record.lifecycle_status = LifecycleStatus.APPROVED.value
        model_record.reviewed_by = reviewer_label
        model_record.review_basis = review_basis
        model_record.review_notes = review_notes
        now = datetime.now(timezone.utc)
        model_record.reviewed_at = now
        model_record.approved_by = reviewer_label
        model_record.approved_at = now
        model_record.updated_at = now

        self.db.commit()
        self.db.refresh(model_record)
        return model_record

    def create_new_draft_version(
        self,
        project_id: str,
        model_id: str,
        new_version: str,
        definition: WorkflowModelDefinition,
        domain: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> C2WorkflowModel:
        """Creates a new DRAFT version for an existing model.

        Enforces:
        - Editing an approved definition creates a new DRAFT version.
        - Unique constraint on (project_id, model_id, new_version).
        - New version starts strictly in DRAFT.
        """
        # Check existing version
        existing = self.db.execute(
            select(C2WorkflowModel).where(
                C2WorkflowModel.project_id == project_id,
                C2WorkflowModel.model_id == model_id,
                C2WorkflowModel.version == new_version,
            )
        ).scalar_one_or_none()

        if existing is not None:
            raise ModelVersionAlreadyExistsError(
                f"Model '{model_id}' version '{new_version}' already exists in project '{project_id}'."
            )

        definition_dict = definition.model_dump(mode="json")
        content_hash = compute_canonical_content_hash(definition_dict)

        new_record = C2WorkflowModel(
            model_id=model_id,
            version=new_version,
            schema_version=definition.schema_version,
            project_id=project_id,
            domain=domain or definition.domain,
            name=name or definition.name,
            description=description or definition.description,
            definition=definition_dict,
            content_hash=content_hash,
            lifecycle_status=LifecycleStatus.DRAFT.value,
        )

        self.db.add(new_record)
        self.db.commit()
        self.db.refresh(new_record)
        return new_record

    def assert_version_mutable(self, model_record: C2WorkflowModel) -> None:
        """Enforces approved-version immutability requirement.

        If a model version reaches APPROVED, it can never be mutated or replaced.
        """
        if model_record.lifecycle_status == LifecycleStatus.APPROVED.value:
            raise ApprovedModelImmutableError(
                f"Model '{model_record.model_id}' version '{model_record.version}' is APPROVED and immutable. "
                "Modifications require creating a new DRAFT version."
            )

    def check_model_readiness(
        self,
        project_id: str,
        model_id: str,
        version: str,
    ) -> ModelReadinessInfo:
        """Assesses model readiness for subsequent test generation and trace alignment.

        CRITICAL REQUIREMENT:
        - If unusable, unapproved, or contradictory, explains why it is MODEL NOT READY.
        - Never introduces a runtime PASS verdict for model validation.
        """
        model_record = self.get_model_version(model_id, version, project_id=project_id)
        latest_val = self.get_latest_validation_report(project_id, model_id, version)

        # Check approval
        if model_record.lifecycle_status != LifecycleStatus.APPROVED.value:
            status_reasons = {
                LifecycleStatus.DRAFT.value: [ReasonCode.MODEL_NOT_READY_UNAPPROVED],
                LifecycleStatus.VALIDATED.value: [
                    ReasonCode.MODEL_NOT_READY_UNAPPROVED
                ],
            }
            return ModelReadinessInfo(
                project_id=project_id,
                model_id=model_id,
                version=version,
                is_ready=False,
                status="MODEL_NOT_READY",
                verdict=EvaluationVerdict.MODEL_NOT_READY,
                reasons=status_reasons.get(
                    model_record.lifecycle_status,
                    [ReasonCode.MODEL_NOT_READY_UNAPPROVED],
                ),
                explanation=(
                    f"Model is in lifecycle status '{model_record.lifecycle_status}' and has not been APPROVED. "
                    "Approved reference oracle status is required for test generation."
                ),
            )

        # Check validation report existence
        if latest_val is None:
            return ModelReadinessInfo(
                project_id=project_id,
                model_id=model_id,
                version=version,
                is_ready=False,
                status="MODEL_NOT_READY",
                verdict=EvaluationVerdict.MODEL_NOT_READY,
                reasons=[ReasonCode.MODEL_NOT_READY_VALIDATION_FAILED],
                explanation="Approved model has no recorded validation evidence.",
            )

        # Check definition hash freshness
        if latest_val.definition_hash != model_record.content_hash:
            return ModelReadinessInfo(
                project_id=project_id,
                model_id=model_id,
                version=version,
                is_ready=False,
                status="MODEL_NOT_READY",
                verdict=EvaluationVerdict.MODEL_NOT_READY,
                reasons=[ReasonCode.MODEL_NOT_READY_STALE_VALIDATION],
                explanation="Model content hash does not match latest validation evidence.",
            )

        # Check blocking validation issues
        if not latest_val.is_valid or latest_val.has_blocking_issues:
            return ModelReadinessInfo(
                project_id=project_id,
                model_id=model_id,
                version=version,
                is_ready=False,
                status="MODEL_NOT_READY",
                verdict=EvaluationVerdict.MODEL_NOT_READY,
                reasons=[ReasonCode.MODEL_NOT_READY_VALIDATION_FAILED],
                explanation="Validation report records active blocking issues.",
            )

        # Model is approved, validated, and structurally sound
        return ModelReadinessInfo(
            project_id=project_id,
            model_id=model_id,
            version=version,
            is_ready=True,
            status="READY",
            verdict=None,  # Never returns runtime PASS for model validation
            reasons=[ReasonCode.OUTCOME_ACHIEVED],
            explanation=(
                f"Model '{model_id}' version '{version}' is validated, approved by '{model_record.approved_by}', "
                "and ready for test generation and trace alignment."
            ),
        )

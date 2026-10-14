"""Service layer for C2 workflow model management and persistence."""

import hashlib
import json
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.components.c2_state_aware_workflow.contracts.efsm import (
    WorkflowModelDefinition,
)
from app.components.c2_state_aware_workflow.contracts.enums import LifecycleStatus
from app.components.c2_state_aware_workflow.models.workflow_model import C2WorkflowModel
from app.components.c2_state_aware_workflow.schemas.api_models import (
    CreateDraftWorkflowModelRequest,
)


class C2ModelServiceError(Exception):
    """Base exception for C2 model service operations."""


class ModelVersionAlreadyExistsError(C2ModelServiceError):
    """Raised when attempting to create a model version that already exists."""


class ModelNotFoundError(C2ModelServiceError):
    """Raised when a requested model version cannot be found."""


class ApprovedModelImmutableError(C2ModelServiceError):
    """Raised when attempting to modify an approved reference model version."""


def compute_canonical_content_hash(
    definition: dict[str, Any] | WorkflowModelDefinition,
) -> str:
    """Computes a deterministic SHA-256 hash from canonical JSON representation.

    Keys are strictly sorted with uniform separators to guarantee hash stability
    across environments and serialization runs.
    """
    if isinstance(definition, WorkflowModelDefinition):
        raw_dict = definition.model_dump(mode="json")
    elif isinstance(definition, dict):
        raw_dict = definition
    else:
        raise ValueError("Definition must be a dictionary or WorkflowModelDefinition.")

    canonical_json = json.dumps(raw_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class WorkflowModelService:
    """Encapsulates database operations and lifecycle invariants for workflow models."""

    def __init__(self, db: Session):
        self.db = db

    def create_draft_model(
        self, request: CreateDraftWorkflowModelRequest
    ) -> C2WorkflowModel:
        """Persists a new workflow model in DRAFT lifecycle state.

        Enforces:
        1. All models created in Phase 1 remain strictly DRAFT.
        2. Unique constraint on (project_id, model_id, version).
        3. Deterministic canonical content hashing.
        """
        def_obj = request.definition
        model_id = def_obj.model_id
        version = def_obj.version

        # Check existing version
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
        """Retrieves a specific workflow model version."""
        stmt = select(C2WorkflowModel).where(
            C2WorkflowModel.model_id == model_id,
            C2WorkflowModel.version == version,
        )
        if project_id:
            stmt = stmt.where(C2WorkflowModel.project_id == project_id)

        record = self.db.execute(stmt).scalar_one_or_none()
        if record is None:
            raise ModelNotFoundError(
                f"Workflow model '{model_id}' version '{version}' not found."
            )
        return record

    def assert_version_mutable(self, model_record: C2WorkflowModel) -> None:
        """Enforces approved-version immutability requirement.

        If a model version reaches APPROVED, it can never be mutated or replaced.
        """
        if model_record.lifecycle_status == LifecycleStatus.APPROVED.value:
            raise ApprovedModelImmutableError(
                f"Model '{model_record.model_id}' version '{model_record.version}' is APPROVED and immutable."
            )

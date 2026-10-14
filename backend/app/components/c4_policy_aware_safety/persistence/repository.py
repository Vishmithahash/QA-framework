"""Persistence repository for C4 entities, enforcing project isolation."""

from sqlalchemy import and_, select
from sqlalchemy.orm import Session
from app.components.c4_policy_aware_safety.contracts.artifacts import (
    ArtifactKind,
    ArtifactSection,
    ArtifactVersion,
)
from app.components.c4_policy_aware_safety.contracts.findings import (
    EvaluationFinding,
)
from app.components.c4_policy_aware_safety.contracts.policy import (
    ContractLifecycleStatus,
    PolicyContract,
    PolicyRule,
)
from app.components.c4_policy_aware_safety.derivation.issues import (
    CandidateValidationIssue,
)
from app.components.c4_policy_aware_safety.persistence.models import (
    C4ArtifactModel,
    C4EvaluationFindingModel,
    C4PolicyContractModel,
    C4PolicyRuleModel,
)


class C4Repository:
    """Repository handling database operations for C4 entities with strict project scoping."""

    def __init__(self, db: Session):
        self.db = db

    # --- Artifacts ---

    def save_artifact(self, artifact: ArtifactVersion) -> C4ArtifactModel:
        """Persist or update an artifact version."""
        existing = self.db.scalar(
            select(C4ArtifactModel).where(
                and_(
                    C4ArtifactModel.project_id == artifact.project_id,
                    C4ArtifactModel.artifact_id == artifact.artifact_id,
                    C4ArtifactModel.version == artifact.version,
                )
            )
        )

        sections_dump = [s.model_dump() for s in artifact.sections]

        if existing:
            existing.kind = artifact.kind.value
            existing.content_hash = artifact.content_hash
            existing.normalized_content = artifact.normalized_content
            existing.sections_json = sections_dump
            existing.metadata_json = artifact.metadata
            model = existing
        else:
            model = C4ArtifactModel(
                project_id=artifact.project_id,
                artifact_id=artifact.artifact_id,
                version=artifact.version,
                kind=artifact.kind.value,
                content_hash=artifact.content_hash,
                normalized_content=artifact.normalized_content,
                sections_json=sections_dump,
                metadata_json=artifact.metadata,
                created_at=artifact.created_at,
            )
            self.db.add(model)

        self.db.commit()
        self.db.refresh(model)
        return model

    def get_artifact(
        self,
        project_id: str,
        artifact_id: str,
        version: str,
    ) -> ArtifactVersion | None:
        """Retrieve an artifact version strictly scoped by project_id."""
        model = self.db.scalar(
            select(C4ArtifactModel).where(
                and_(
                    C4ArtifactModel.project_id == project_id,
                    C4ArtifactModel.artifact_id == artifact_id,
                    C4ArtifactModel.version == version,
                )
            )
        )
        if not model:
            return None

        sections = [ArtifactSection.model_validate(s) for s in model.sections_json]
        return ArtifactVersion(
            project_id=model.project_id,
            artifact_id=model.artifact_id,
            version=model.version,
            kind=ArtifactKind(model.kind),
            content_hash=model.content_hash,
            normalized_content=model.normalized_content,
            sections=sections,
            created_at=model.created_at,
            metadata=model.metadata_json,
        )

    def list_artifacts(self, project_id: str) -> list[ArtifactVersion]:
        """List all artifact versions for a project."""
        models = self.db.scalars(
            select(C4ArtifactModel).where(C4ArtifactModel.project_id == project_id)
        ).all()
        result = []
        for model in models:
            sections = [ArtifactSection.model_validate(s) for s in model.sections_json]
            result.append(
                ArtifactVersion(
                    project_id=model.project_id,
                    artifact_id=model.artifact_id,
                    version=model.version,
                    kind=ArtifactKind(model.kind),
                    content_hash=model.content_hash,
                    normalized_content=model.normalized_content,
                    sections=sections,
                    created_at=model.created_at,
                    metadata=model.metadata_json,
                )
            )
        return result

    # --- Contracts & Rules ---

    def save_contract(self, contract: PolicyContract) -> C4PolicyContractModel:
        """Persist or update a policy contract and its constituent rules."""
        existing = self.db.scalar(
            select(C4PolicyContractModel).where(
                and_(
                    C4PolicyContractModel.project_id == contract.project_id,
                    C4PolicyContractModel.contract_id == contract.contract_id,
                    C4PolicyContractModel.version == contract.version,
                )
            )
        )

        validation_issues_dump = [i.model_dump() for i in contract.validation_issues]

        if existing:
            existing.lifecycle_status = contract.lifecycle_status.value
            existing.content_hash = contract.content_hash
            existing.referenced_artifact_versions_json = (
                contract.referenced_artifact_versions
            )
            existing.validation_issues_json = validation_issues_dump
            existing.acceptance_metadata_json = contract.acceptance_metadata
            existing.updated_at = contract.updated_at
            # Replace rules
            existing.rules.clear()
            contract_model = existing
        else:
            contract_model = C4PolicyContractModel(
                project_id=contract.project_id,
                contract_id=contract.contract_id,
                version=contract.version,
                lifecycle_status=contract.lifecycle_status.value,
                content_hash=contract.content_hash,
                referenced_artifact_versions_json=contract.referenced_artifact_versions,
                validation_issues_json=validation_issues_dump,
                acceptance_metadata_json=contract.acceptance_metadata,
                created_at=contract.created_at,
                updated_at=contract.updated_at,
            )
            self.db.add(contract_model)
            self.db.flush()

        for rule in contract.rules:
            rule_model = C4PolicyRuleModel(
                contract_db_id=contract_model.id,
                rule_id=rule.rule_id,
                rule_version=rule.rule_version,
                family=rule.family.value,
                evaluation_boundary=rule.evaluation_boundary.value,
                severity=rule.severity.value,
                status=rule.status.value,
                rule_json=rule.model_dump(mode="json"),
            )
            self.db.add(rule_model)

        self.db.commit()
        self.db.refresh(contract_model)
        return contract_model

    def get_contract(
        self,
        project_id: str,
        contract_id: str,
        version: int,
    ) -> PolicyContract | None:
        """Retrieve a specific policy contract version scoped by project_id."""
        model = self.db.scalar(
            select(C4PolicyContractModel).where(
                and_(
                    C4PolicyContractModel.project_id == project_id,
                    C4PolicyContractModel.contract_id == contract_id,
                    C4PolicyContractModel.version == version,
                )
            )
        )
        if not model:
            return None

        rules = [PolicyRule.model_validate(r.rule_json) for r in model.rules]
        issues = [
            CandidateValidationIssue.model_validate(i)
            for i in model.validation_issues_json
        ]

        return PolicyContract(
            contract_id=model.contract_id,
            project_id=model.project_id,
            version=model.version,
            lifecycle_status=ContractLifecycleStatus(model.lifecycle_status),
            rules=rules,
            referenced_artifact_versions=model.referenced_artifact_versions_json,
            content_hash=model.content_hash,
            validation_issues=issues,
            acceptance_metadata=model.acceptance_metadata_json,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    # --- Findings ---

    def save_findings(
        self, findings: list[EvaluationFinding]
    ) -> list[C4EvaluationFindingModel]:
        """Persist evaluation findings."""
        models: list[C4EvaluationFindingModel] = []
        for finding in findings:
            model = C4EvaluationFindingModel(
                finding_id=finding.finding_id,
                project_id=finding.project_id,
                case_id=finding.case_id,
                run_id=finding.run_id,
                contract_id=finding.contract_id,
                contract_version=finding.contract_version,
                rule_id=finding.rule_id,
                rule_version=finding.rule_version,
                verdict=finding.verdict.value,
                violation_stage=finding.violation_stage.value
                if finding.violation_stage
                else None,
                severity=finding.severity.value,
                finding_json=finding.model_dump(mode="json"),
            )
            self.db.add(model)
            models.append(model)

        self.db.commit()
        return models

    def get_findings(
        self,
        project_id: str,
        case_id: str | None = None,
        run_id: str | None = None,
    ) -> list[EvaluationFinding]:
        """Query evaluation findings with project, case, and run filters."""
        stmt = select(C4EvaluationFindingModel).where(
            C4EvaluationFindingModel.project_id == project_id
        )
        if case_id:
            stmt = stmt.where(C4EvaluationFindingModel.case_id == case_id)
        if run_id:
            stmt = stmt.where(C4EvaluationFindingModel.run_id == run_id)

        models = self.db.scalars(stmt).all()
        return [EvaluationFinding.model_validate(m.finding_json) for m in models]

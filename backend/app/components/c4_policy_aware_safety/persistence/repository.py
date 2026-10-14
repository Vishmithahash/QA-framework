"""Persistence repository for C4 entities, enforcing project isolation."""

from datetime import datetime, timezone
from sqlalchemy import and_, select
from sqlalchemy.orm import Session
from app.components.c4_policy_aware_safety.contracts.artifacts import (
    ArtifactKind,
    ArtifactSection,
    ArtifactVersion,
)
from app.components.c4_policy_aware_safety.contracts.domain_binding import DomainBinding
from app.components.c4_policy_aware_safety.contracts.findings import (
    EvaluationFinding,
)
from app.components.c4_policy_aware_safety.contracts.policy import (
    ContractLifecycleStatus,
    PolicyContract,
    PolicyRule,
)
from app.components.c4_policy_aware_safety.contracts.test_cases import (
    GeneratedTestCase,
    TestCaseLifecycleStatus,
)
from app.components.c4_policy_aware_safety.derivation.issues import (
    CandidateValidationIssue,
)
from app.components.c4_policy_aware_safety.generation.report import (
    C4GenerationBatchReport,
)
from app.components.c4_policy_aware_safety.persistence.models import (
    C4ArtifactModel,
    C4DomainBindingModel,
    C4EvaluationFindingModel,
    C4GenerationBatchModel,
    C4PolicyContractModel,
    C4PolicyRuleModel,
    C4TestCaseModel,
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
            if existing.lifecycle_status == ContractLifecycleStatus.ACCEPTED.value:
                # Disallow modifying rules, content hash, or status of an already-accepted contract
                if (
                    existing.content_hash != contract.compute_content_hash()
                    or contract.lifecycle_status != ContractLifecycleStatus.ACCEPTED
                ):
                    raise ValueError(
                        f"Cannot modify accepted policy contract '{contract.contract_id}' (v{contract.version}). "
                        "Accepted contracts are immutable. Create a new contract version instead."
                    )
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

    # --- Domain Bindings (Phase 2) ---

    def save_domain_binding(self, binding: DomainBinding) -> C4DomainBindingModel:
        """Persist or update a domain binding."""
        existing = self.db.scalar(
            select(C4DomainBindingModel).where(
                and_(
                    C4DomainBindingModel.project_id == binding.project_id,
                    C4DomainBindingModel.domain_id == binding.domain_id,
                    C4DomainBindingModel.version == binding.binding_version,
                )
            )
        )

        binding_dump = binding.model_dump(mode="json")

        if existing:
            existing.description = binding.description
            existing.binding_json = binding_dump
            model = existing
        else:
            model = C4DomainBindingModel(
                project_id=binding.project_id,
                domain_id=binding.domain_id,
                version=binding.binding_version,
                description=binding.description,
                binding_json=binding_dump,
                created_at=binding.created_at,
            )
            self.db.add(model)

        self.db.commit()
        self.db.refresh(model)
        return model

    def get_domain_binding(
        self, project_id: str, domain_id: str, version: str
    ) -> DomainBinding | None:
        """Retrieve a specific domain binding scoped by project_id."""
        model = self.db.scalar(
            select(C4DomainBindingModel).where(
                and_(
                    C4DomainBindingModel.project_id == project_id,
                    C4DomainBindingModel.domain_id == domain_id,
                    C4DomainBindingModel.version == version,
                )
            )
        )
        if not model:
            return None
        return DomainBinding.model_validate(model.binding_json)

    def list_domain_bindings(self, project_id: str) -> list[DomainBinding]:
        """List all domain bindings for a project."""
        models = self.db.scalars(
            select(C4DomainBindingModel).where(
                C4DomainBindingModel.project_id == project_id
            )
        ).all()
        return [DomainBinding.model_validate(m.binding_json) for m in models]

    # --- Generation Batches (Phase 2) ---

    def save_generation_batch(
        self, report: C4GenerationBatchReport
    ) -> C4GenerationBatchModel:
        """Persist generation batch report."""
        existing = self.db.scalar(
            select(C4GenerationBatchModel).where(
                and_(
                    C4GenerationBatchModel.project_id == report.project_id,
                    C4GenerationBatchModel.batch_id == report.batch_id,
                )
            )
        )
        report_dump = report.model_dump(mode="json")
        if existing:
            existing.report_json = report_dump
            existing.total_cases = report.total_cases_generated
            model = existing
        else:
            model = C4GenerationBatchModel(
                batch_id=report.batch_id,
                project_id=report.project_id,
                contract_id=report.contract_id,
                contract_version=report.contract_version,
                domain_id=report.domain_id,
                domain_binding_version=report.domain_binding_version,
                total_cases=report.total_cases_generated,
                report_json=report_dump,
                created_at=report.generated_at,
            )
            self.db.add(model)

        self.db.commit()
        self.db.refresh(model)
        return model

    def get_generation_batch(
        self, project_id: str, batch_id: str
    ) -> C4GenerationBatchReport | None:
        """Retrieve a generation batch report."""
        model = self.db.scalar(
            select(C4GenerationBatchModel).where(
                and_(
                    C4GenerationBatchModel.project_id == project_id,
                    C4GenerationBatchModel.batch_id == batch_id,
                )
            )
        )
        if not model:
            return None
        return C4GenerationBatchReport.model_validate(model.report_json)

    def list_generation_batches(self, project_id: str) -> list[C4GenerationBatchReport]:
        """List all generation batches for a project."""
        models = self.db.scalars(
            select(C4GenerationBatchModel).where(
                C4GenerationBatchModel.project_id == project_id
            )
        ).all()
        return [C4GenerationBatchReport.model_validate(m.report_json) for m in models]

    # --- Test Cases & Freeze Operations (Phase 2) ---

    def save_test_case(self, case: GeneratedTestCase) -> C4TestCaseModel:
        """Persist or update a test case, enforcing immutability of frozen cases."""
        existing = self.db.scalar(
            select(C4TestCaseModel).where(
                and_(
                    C4TestCaseModel.project_id == case.project_id,
                    C4TestCaseModel.case_id == case.case_id,
                    C4TestCaseModel.version == case.version,
                )
            )
        )

        case_dump = case.model_dump(mode="json")

        if existing:
            if existing.lifecycle_status == TestCaseLifecycleStatus.FROZEN.value:
                # Do not allow modifying frozen case content or demoting status
                if (
                    existing.content_hash != case.compute_content_hash()
                    or case.lifecycle_status != TestCaseLifecycleStatus.FROZEN
                ):
                    raise ValueError(
                        f"Cannot modify frozen test case '{case.case_id}' (v{case.version}). "
                        "Frozen cases are immutable."
                    )

            existing.lifecycle_status = case.lifecycle_status.value
            existing.content_hash = case.content_hash
            existing.case_json = case_dump
            existing.updated_at = case.updated_at
            model = existing
        else:
            model = C4TestCaseModel(
                case_id=case.case_id,
                version=case.version,
                project_id=case.project_id,
                batch_id=case.batch_id,
                domain_id=case.domain_id,
                category=case.category.value,
                scenario_id=case.scenario_id,
                lifecycle_status=case.lifecycle_status.value,
                content_hash=case.content_hash,
                case_json=case_dump,
                created_at=case.created_at,
                updated_at=case.updated_at,
            )
            self.db.add(model)

        self.db.commit()
        self.db.refresh(model)
        return model

    def get_test_case(
        self, project_id: str, case_id: str, version: int
    ) -> GeneratedTestCase | None:
        """Retrieve a specific test case version."""
        model = self.db.scalar(
            select(C4TestCaseModel).where(
                and_(
                    C4TestCaseModel.project_id == project_id,
                    C4TestCaseModel.case_id == case_id,
                    C4TestCaseModel.version == version,
                )
            )
        )
        if not model:
            return None
        return GeneratedTestCase.model_validate(model.case_json)

    def list_test_cases(
        self,
        project_id: str,
        batch_id: str | None = None,
        category: str | None = None,
        status: str | None = None,
    ) -> list[GeneratedTestCase]:
        """List test cases matching filters."""
        stmt = select(C4TestCaseModel).where(C4TestCaseModel.project_id == project_id)
        if batch_id:
            stmt = stmt.where(C4TestCaseModel.batch_id == batch_id)
        if category:
            stmt = stmt.where(C4TestCaseModel.category == category)
        if status:
            stmt = stmt.where(C4TestCaseModel.lifecycle_status == status)

        models = self.db.scalars(stmt).all()
        return [GeneratedTestCase.model_validate(m.case_json) for m in models]

    def freeze_test_case(
        self,
        project_id: str,
        case_id: str,
        version: int,
    ) -> GeneratedTestCase:
        """
        Transition a VALIDATED test case to FROZEN.
        Re-verifies contract status and enforces immutability.
        """
        case = self.get_test_case(project_id, case_id, version)
        if not case:
            raise ValueError(
                f"Test case '{case_id}' (v{version}) not found in project '{project_id}'."
            )

        # Recheck contract is still ACCEPTED
        contract = self.get_contract(
            project_id, case.contract_id, case.contract_version
        )
        if (
            not contract
            or contract.lifecycle_status != ContractLifecycleStatus.ACCEPTED
        ):
            raise ValueError(
                f"Cannot freeze test case '{case_id}': targeted contract '{case.contract_id}' "
                f"(v{case.contract_version}) is not in ACCEPTED status."
            )

        if case.lifecycle_status != TestCaseLifecycleStatus.VALIDATED:
            raise ValueError(
                f"Cannot freeze test case '{case_id}': case must be in VALIDATED status, "
                f"got '{case.lifecycle_status}'."
            )

        now = datetime.now(timezone.utc)
        case.lifecycle_status = TestCaseLifecycleStatus.FROZEN
        case.updated_at = now
        case.content_hash = case.compute_content_hash()
        self.save_test_case(case)
        return case

    def freeze_batch(
        self,
        project_id: str,
        batch_id: str,
    ) -> list[GeneratedTestCase]:
        """Freeze all VALIDATED cases in a generation batch."""
        cases = self.list_test_cases(project_id, batch_id=batch_id)
        frozen_cases: list[GeneratedTestCase] = []
        for c in cases:
            if c.lifecycle_status == TestCaseLifecycleStatus.VALIDATED:
                frozen = self.freeze_test_case(project_id, c.case_id, c.version)
                frozen_cases.append(frozen)
            elif c.lifecycle_status == TestCaseLifecycleStatus.FROZEN:
                frozen_cases.append(c)
        return frozen_cases

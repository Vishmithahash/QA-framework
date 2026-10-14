"""C1 Validation Service orchestrating project and candidate validation."""

from typing import Optional

from ..contracts.base import CaseReadiness
from ..contracts.candidate_case import CandidateTestCase, ValidationIssue
from ..contracts.project_input import ProjectInput
from ..validators.candidate_validator import validate_candidate_case
from ..validators.project_validator import validate_project_input


class C1ValidationService:
    """Pure validation service for C1 project inputs and candidate test cases (FR-01/FR-03).

    This service operates purely in-memory without contacting external systems, databases,
    or networks. It verifies integrity, JSON schemas, references, and assertion structures.
    """

    def validate_project(
        self, project_input: ProjectInput
    ) -> tuple[bool, list[ValidationIssue]]:
        """Validate a complete project input bundle.

        Returns:
            (is_valid, issues): True if no ERROR-level issues are present.
        """
        issues = validate_project_input(project_input)
        has_errors = any(issue.severity == "ERROR" for issue in issues)
        return not has_errors, issues

    def validate_candidate(
        self,
        candidate: CandidateTestCase,
        project_input: Optional[ProjectInput] = None,
    ) -> tuple[CaseReadiness, list[ValidationIssue]]:
        """Validate candidate test expectations against project specification.

        Returns:
            (readiness, issues): READY if eligible for execution, NOT_READY otherwise.
        """
        issues = validate_candidate_case(candidate, project_input)
        has_errors = any(issue.severity == "ERROR" for issue in issues)
        readiness = CaseReadiness.NOT_READY if has_errors else CaseReadiness.READY
        return readiness, issues

    def prepare_and_freeze_candidate(
        self,
        candidate: CandidateTestCase,
        project_input: Optional[ProjectInput] = None,
    ) -> CandidateTestCase:
        """Evaluate candidate readiness, attach validation issues, and return updated case.

        If validation issues exist, case readiness is set to NOT_READY and the case is
        excluded from evaluation scoring. It is never treated as an agent failure (FR-03).
        """
        readiness, issues = self.validate_candidate(candidate, project_input)
        updated_case = candidate.model_copy(
            update={
                "readiness": readiness,
                "validation_issues": issues,
            }
        )
        return updated_case

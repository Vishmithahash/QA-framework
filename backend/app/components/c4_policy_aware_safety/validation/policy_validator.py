"""Validation service for candidate rules and policy contracts."""

from app.components.c4_policy_aware_safety.contracts.artifacts import ArtifactVersion
from app.components.c4_policy_aware_safety.contracts.policy import (
    ContractLifecycleStatus,
    PolicyContract,
    PolicyRequirement,
    PolicyRule,
    RuleLifecycleStatus,
)
from app.components.c4_policy_aware_safety.contracts.predicates import (
    AtomicPredicate,
    CompoundPredicate,
    DeclarativePredicate,
    PredicateOperator,
)
from app.components.c4_policy_aware_safety.derivation.issues import (
    CandidateValidationIssue,
    IssueCode,
)


class PolicyContractValidator:
    """Validates policy contracts, source provenance, predicates, and structural conflicts."""

    def __init__(
        self,
        artifacts_by_key: dict[tuple[str, str, str], ArtifactVersion] | None = None,
    ):
        """
        artifacts_by_key maps (project_id, artifact_id, version) -> ArtifactVersion.
        """
        self.artifacts = artifacts_by_key or {}

    def add_artifact(self, artifact: ArtifactVersion) -> None:
        key = (artifact.project_id, artifact.artifact_id, artifact.version)
        self.artifacts[key] = artifact

    def validate_predicate(
        self,
        pred: DeclarativePredicate | None,
        rule_id: str,
        path: str = "applicability",
    ) -> list[CandidateValidationIssue]:
        """Validate that predicate uses allowlisted fields and valid operators."""
        if pred is None:
            return []

        issues: list[CandidateValidationIssue] = []

        if isinstance(pred, AtomicPredicate):
            # Allowlist field characters: alphanumerics, dots, underscores
            if not pred.field or not all(c.isalnum() or c in "._" for c in pred.field):
                issues.append(
                    CandidateValidationIssue(
                        code=IssueCode.UNSUPPORTED,
                        message=f"Disallowed field path '{pred.field}' in {path}.",
                        rule_id=rule_id,
                        field=f"{path}.field",
                    )
                )

            # Ensure operator is allowlisted
            if not isinstance(pred.operator, PredicateOperator):
                issues.append(
                    CandidateValidationIssue(
                        code=IssueCode.UNSUPPORTED,
                        message=f"Invalid operator '{pred.operator}' in {path}.",
                        rule_id=rule_id,
                        field=f"{path}.operator",
                    )
                )

        elif isinstance(pred, CompoundPredicate):
            if pred.operator not in (
                PredicateOperator.ALL,
                PredicateOperator.ANY,
                PredicateOperator.NOT,
            ):
                issues.append(
                    CandidateValidationIssue(
                        code=IssueCode.UNSUPPORTED,
                        message=f"Compound operator must be 'all', 'any', or 'not', got '{pred.operator}'.",
                        rule_id=rule_id,
                        field=f"{path}.operator",
                    )
                )
            if not pred.predicates:
                issues.append(
                    CandidateValidationIssue(
                        code=IssueCode.AMBIGUOUS,
                        message=f"Compound predicate '{pred.operator}' has no child predicates.",
                        rule_id=rule_id,
                        field=f"{path}.predicates",
                    )
                )
            for idx, child in enumerate(pred.predicates):
                issues.extend(
                    self.validate_predicate(child, rule_id, f"{path}.predicates[{idx}]")
                )

        return issues

    def validate_rule(
        self,
        rule: PolicyRule,
        project_id: str,
    ) -> list[CandidateValidationIssue]:
        """Validate a single candidate rule against source artifacts and schema rules."""
        issues: list[CandidateValidationIssue] = []

        # 1. Source reference presence
        if not rule.sources:
            issues.append(
                CandidateValidationIssue(
                    code=IssueCode.MISSING_SOURCE,
                    message=f"Rule '{rule.rule_id}' has no supporting source references.",
                    rule_id=rule.rule_id,
                    field="sources",
                )
            )
            return issues

        # 2. Source references must exist in the SAME project and version, with matching excerpt
        for idx, src in enumerate(rule.sources):
            key = (project_id, src.artifact_id, src.artifact_version)
            artifact = self.artifacts.get(key)

            if artifact is None:
                issues.append(
                    CandidateValidationIssue(
                        code=IssueCode.INVALID_REFERENCE,
                        message=(
                            f"Rule '{rule.rule_id}' references non-existent or cross-project artifact "
                            f"(project='{project_id}', artifact_id='{src.artifact_id}', version='{src.artifact_version}')."
                        ),
                        rule_id=rule.rule_id,
                        field=f"sources[{idx}].artifact_id",
                    )
                )
                continue

            # Verify excerpt agreement
            if not src.matches_content(artifact.normalized_content):
                issues.append(
                    CandidateValidationIssue(
                        code=IssueCode.INVALID_REFERENCE,
                        message=(
                            f"Excerpt in rule '{rule.rule_id}' does not match content in "
                            f"artifact '{src.artifact_id}' (version {src.artifact_version})."
                        ),
                        rule_id=rule.rule_id,
                        field=f"sources[{idx}].supporting_excerpt",
                    )
                )

        # 3. Predicate validation
        issues.extend(
            self.validate_predicate(rule.applicability, rule.rule_id, "applicability")
        )
        issues.extend(
            self.validate_predicate(
                rule.compliance_condition, rule.rule_id, "compliance_condition"
            )
        )
        issues.extend(
            self.validate_predicate(
                rule.violation_condition, rule.rule_id, "violation_condition"
            )
        )

        return issues

    def detect_conflicts(
        self, rules: list[PolicyRule]
    ) -> list[CandidateValidationIssue]:
        """Detect straightforward logical contradictions between rules within the supported subset."""
        issues: list[CandidateValidationIssue] = []
        n = len(rules)

        for i in range(n):
            for j in range(i + 1, n):
                r1 = rules[i]
                r2 = rules[j]

                # Check duplicate rule IDs
                if r1.rule_id == r2.rule_id:
                    issues.append(
                        CandidateValidationIssue(
                            code=IssueCode.CONFLICTING,
                            message=f"Duplicate rule identifier detected: '{r1.rule_id}'.",
                            rule_id=r1.rule_id,
                        )
                    )
                    continue

                # Check straightforward conflicts: identical selectors + boundary + applicability, but opposing requirements
                same_principal = (
                    r1.principal_selector.role == r2.principal_selector.role
                )
                same_action = r1.action_selector.action == r2.action_selector.action
                same_resource = (
                    r1.resource_selector.resource_type
                    == r2.resource_selector.resource_type
                )
                same_boundary = r1.evaluation_boundary == r2.evaluation_boundary
                same_applicability = r1.applicability == r2.applicability

                if (
                    same_principal
                    and same_action
                    and same_resource
                    and same_boundary
                    and same_applicability
                ):
                    if (
                        r1.requirement == PolicyRequirement.ALLOW
                        and r2.requirement == PolicyRequirement.DENY
                    ) or (
                        r1.requirement == PolicyRequirement.DENY
                        and r2.requirement == PolicyRequirement.ALLOW
                    ):
                        issues.append(
                            CandidateValidationIssue(
                                code=IssueCode.CONFLICTING,
                                message=(
                                    f"Direct policy conflict between rule '{r1.rule_id}' ({r1.requirement}) "
                                    f"and rule '{r2.rule_id}' ({r2.requirement}) on same target boundary."
                                ),
                                rule_id=r1.rule_id,
                            )
                        )

        return issues

    def validate_contract(self, contract: PolicyContract) -> PolicyContract:
        """
        Validate entire policy contract.
        Updates validation_issues and transitions status from DRAFT -> VALIDATED if clean.
        """
        issues: list[CandidateValidationIssue] = []

        # Validate each rule individually
        for rule in contract.rules:
            rule_issues = self.validate_rule(rule, contract.project_id)
            if not rule_issues:
                rule.status = RuleLifecycleStatus.VALIDATED
            issues.extend(rule_issues)

        # Detect cross-rule conflicts and duplicate IDs
        issues.extend(self.detect_conflicts(contract.rules))

        contract.validation_issues = issues

        # Lifecycle transition: If no blocking issues, mark VALIDATED
        blocking_issues = [iss for iss in issues if iss.blocking]
        if not blocking_issues:
            contract.lifecycle_status = ContractLifecycleStatus.VALIDATED
        else:
            contract.lifecycle_status = ContractLifecycleStatus.DRAFT

        # Recompute canonical content hash
        contract.content_hash = contract.compute_content_hash()
        return contract

"""Unit tests for C4 contract validation, source provenance checks, and acceptance."""

import pytest
from app.components.c4_policy_aware_safety.acceptance.contract_service import (
    ContractAcceptanceService,
)
from app.components.c4_policy_aware_safety.contracts.artifacts import (
    ArtifactKind,
    ArtifactVersion,
)
from app.components.c4_policy_aware_safety.contracts.policy import (
    ActionSelector,
    ContractLifecycleStatus,
    EvaluationBoundary,
    PolicyContract,
    PolicyFamily,
    PolicyRequirement,
    PolicyRule,
    PrincipalSelector,
    ResourceSelector,
    RuleLifecycleStatus,
)
from app.components.c4_policy_aware_safety.contracts.sources import SourceReference
from app.components.c4_policy_aware_safety.derivation.issues import IssueCode
from app.components.c4_policy_aware_safety.validation.policy_validator import (
    PolicyContractValidator,
)


@pytest.fixture
def registered_artifact():
    content = "Role CUSTOMER_SUPPORT must not issue_refund orders where amount > 5000."
    return ArtifactVersion(
        project_id="proj-alpha",
        artifact_id="art-policy-1",
        version="1.0.0",
        kind=ArtifactKind.POLICY_DOCUMENT,
        content_hash=ArtifactVersion.compute_content_hash(content),
        normalized_content=content,
    )


def test_valid_source_reference_passes_validation(registered_artifact):
    """Valid source reference matching registered artifact in same project passes."""
    rule = PolicyRule(
        rule_id="rule-valid-1",
        rule_version=1,
        family=PolicyFamily.AUTHORIZATION,
        principal_selector=PrincipalSelector(role="CUSTOMER_SUPPORT"),
        action_selector=ActionSelector(action="issue_refund"),
        resource_selector=ResourceSelector(resource_type="orders"),
        requirement=PolicyRequirement.DENY,
        evaluation_boundary=EvaluationBoundary.ATTEMPTED_ACTION,
        sources=[
            SourceReference(
                artifact_id="art-policy-1",
                artifact_version="1.0.0",
                supporting_excerpt="Role CUSTOMER_SUPPORT must not issue_refund orders where amount > 5000.",
            )
        ],
    )

    contract = PolicyContract(
        contract_id="contract-1",
        project_id="proj-alpha",
        version=1,
        rules=[rule],
    )

    validator = PolicyContractValidator()
    validator.add_artifact(registered_artifact)

    validated = validator.validate_contract(contract)

    assert len(validated.validation_issues) == 0
    assert validated.lifecycle_status == ContractLifecycleStatus.VALIDATED
    assert validated.rules[0].status == RuleLifecycleStatus.VALIDATED


def test_cross_project_reference_rejection(registered_artifact):
    """Rule referencing an artifact belonging to a different project must be rejected."""
    rule = PolicyRule(
        rule_id="rule-cross-proj",
        rule_version=1,
        family=PolicyFamily.AUTHORIZATION,
        principal_selector=PrincipalSelector(role="CUSTOMER_SUPPORT"),
        action_selector=ActionSelector(action="issue_refund"),
        resource_selector=ResourceSelector(resource_type="orders"),
        requirement=PolicyRequirement.DENY,
        evaluation_boundary=EvaluationBoundary.ATTEMPTED_ACTION,
        sources=[
            SourceReference(
                artifact_id="art-policy-1",
                artifact_version="1.0.0",
                supporting_excerpt="Role CUSTOMER_SUPPORT must not issue_refund orders where amount > 5000.",
            )
        ],
    )

    # Contract is in proj-bravo, but artifact is in proj-alpha
    contract = PolicyContract(
        contract_id="contract-cross",
        project_id="proj-bravo",
        version=1,
        rules=[rule],
    )

    validator = PolicyContractValidator()
    validator.add_artifact(registered_artifact)

    validated = validator.validate_contract(contract)

    assert len(validated.validation_issues) >= 1
    assert validated.validation_issues[0].code == IssueCode.INVALID_REFERENCE
    assert "cross-project" in validated.validation_issues[0].message
    assert validated.lifecycle_status == ContractLifecycleStatus.DRAFT


def test_mismatched_excerpt_rejection(registered_artifact):
    """Rule with an excerpt that does not exist in the source artifact must be rejected."""
    rule = PolicyRule(
        rule_id="rule-bad-excerpt",
        rule_version=1,
        family=PolicyFamily.AUTHORIZATION,
        principal_selector=PrincipalSelector(role="CUSTOMER_SUPPORT"),
        action_selector=ActionSelector(action="issue_refund"),
        resource_selector=ResourceSelector(resource_type="orders"),
        requirement=PolicyRequirement.DENY,
        evaluation_boundary=EvaluationBoundary.ATTEMPTED_ACTION,
        sources=[
            SourceReference(
                artifact_id="art-policy-1",
                artifact_version="1.0.0",
                supporting_excerpt="This excerpt was completely fabricated.",
            )
        ],
    )

    contract = PolicyContract(
        contract_id="contract-bad-exc", project_id="proj-alpha", version=1, rules=[rule]
    )
    validator = PolicyContractValidator()
    validator.add_artifact(registered_artifact)

    validated = validator.validate_contract(contract)

    assert len(validated.validation_issues) >= 1
    assert validated.validation_issues[0].code == IssueCode.INVALID_REFERENCE
    assert "does not match content" in validated.validation_issues[0].message


def test_duplicate_rule_id_and_conflict_detection(registered_artifact):
    """Duplicate rule IDs and direct ALLOW vs DENY contradictions must be flagged as CONFLICTING."""
    source_ref = SourceReference(
        artifact_id="art-policy-1",
        artifact_version="1.0.0",
        supporting_excerpt="Role CUSTOMER_SUPPORT must not issue_refund orders where amount > 5000.",
    )

    # 1. Duplicate ID check
    r1 = PolicyRule(
        rule_id="rule-dup",
        family=PolicyFamily.AUTHORIZATION,
        principal_selector=PrincipalSelector(role="CUSTOMER_SUPPORT"),
        action_selector=ActionSelector(action="issue_refund"),
        resource_selector=ResourceSelector(resource_type="orders"),
        requirement=PolicyRequirement.DENY,
        evaluation_boundary=EvaluationBoundary.ATTEMPTED_ACTION,
        sources=[source_ref],
    )
    r2 = PolicyRule(
        rule_id="rule-dup",  # Duplicate!
        family=PolicyFamily.AUTHORIZATION,
        principal_selector=PrincipalSelector(role="CUSTOMER_SUPPORT"),
        action_selector=ActionSelector(action="issue_refund"),
        resource_selector=ResourceSelector(resource_type="orders"),
        requirement=PolicyRequirement.ALLOW,
        evaluation_boundary=EvaluationBoundary.ATTEMPTED_ACTION,
        sources=[source_ref],
    )

    contract = PolicyContract(
        contract_id="contract-conflict", project_id="proj-alpha", rules=[r1, r2]
    )
    validator = PolicyContractValidator()
    validator.add_artifact(registered_artifact)

    validated = validator.validate_contract(contract)

    dup_issues = [
        i for i in validated.validation_issues if i.code == IssueCode.CONFLICTING
    ]
    assert len(dup_issues) >= 1
    assert "Duplicate rule identifier" in dup_issues[0].message


def test_explicit_acceptance_and_version_immutability(registered_artifact):
    """Contract must be VALIDATED to be accepted; editing accepted contract creates new version."""
    source_ref = SourceReference(
        artifact_id="art-policy-1",
        artifact_version="1.0.0",
        supporting_excerpt="Role CUSTOMER_SUPPORT must not issue_refund orders where amount > 5000.",
    )

    rule = PolicyRule(
        rule_id="rule-accept-1",
        family=PolicyFamily.AUTHORIZATION,
        principal_selector=PrincipalSelector(role="CUSTOMER_SUPPORT"),
        action_selector=ActionSelector(action="issue_refund"),
        resource_selector=ResourceSelector(resource_type="orders"),
        requirement=PolicyRequirement.DENY,
        evaluation_boundary=EvaluationBoundary.ATTEMPTED_ACTION,
        sources=[source_ref],
    )

    contract = PolicyContract(
        contract_id="contract-lifecycle",
        project_id="proj-alpha",
        version=1,
        rules=[rule],
    )

    # Attempting to accept a DRAFT contract fails
    with pytest.raises(ValueError, match="must be VALIDATED"):
        ContractAcceptanceService.accept_contract(
            contract, "QA_LEAD", "Attempting premature accept"
        )

    # Validate first
    validator = PolicyContractValidator()
    validator.add_artifact(registered_artifact)
    validated = validator.validate_contract(contract)
    assert validated.lifecycle_status == ContractLifecycleStatus.VALIDATED

    # Now explicit acceptance succeeds
    accepted = ContractAcceptanceService.accept_contract(
        validated,
        accepted_by="SECURITY_OFFICER_1",
        justification="Verified against security policy artifact v1.0.0",
    )
    assert accepted.lifecycle_status == ContractLifecycleStatus.ACCEPTED
    assert accepted.rules[0].status == RuleLifecycleStatus.ACCEPTED
    assert accepted.acceptance_metadata["accepted_by"] == "SECURITY_OFFICER_1"

    # Fork to new version when modifications are needed
    v2_contract = ContractAcceptanceService.create_new_version(accepted)
    assert v2_contract.version == 2
    assert v2_contract.lifecycle_status == ContractLifecycleStatus.DRAFT
    assert v2_contract.rules[0].rule_version == 2
    assert v2_contract.rules[0].status == RuleLifecycleStatus.CANDIDATE

    # Original v1 remains ACCEPTED and immutable
    assert accepted.version == 1
    assert accepted.lifecycle_status == ContractLifecycleStatus.ACCEPTED

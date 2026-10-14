"""Independent static validator for generated test cases in Component 4 Phase 2.

Independently inspects generated test case artifacts, structural satisfiability,
dependency completeness, evidence capabilities, and prompt separation
without trusting generator-supplied flags.
"""

from app.components.c4_policy_aware_safety.contracts.domain_binding import (
    DomainBinding,
)
from app.components.c4_policy_aware_safety.contracts.evidence import (
    TrustClassification,
)
from app.components.c4_policy_aware_safety.contracts.policy import (
    ContractLifecycleStatus,
    PolicyContract,
    PolicyFamily,
)
from app.components.c4_policy_aware_safety.contracts.test_cases import (
    CaseValidationIssue,
    GeneratedTestCase,
    TestCaseLifecycleStatus,
)


class GeneratedCaseValidator:
    """
    Independent static validator enforcing structural, semantic, and dependency integrity
    for generated test cases prior to execution or freezing.
    """

    def validate_case(
        self,
        case: GeneratedTestCase,
        contract: PolicyContract,
        domain_binding: DomainBinding,
    ) -> GeneratedTestCase:
        """
        Validate an individual test case against accepted policy contract and domain binding.
        Updates readiness_issues and transitions status from DRAFT -> VALIDATED or REJECTED.
        """
        issues: list[CaseValidationIssue] = []

        # 1. Project and domain consistency
        if case.project_id != contract.project_id:
            issues.append(
                CaseValidationIssue(
                    code="PROJECT_MISMATCH",
                    message=(
                        f"Case project_id '{case.project_id}' does not match "
                        f"contract project_id '{contract.project_id}'."
                    ),
                    field="project_id",
                    blocking=True,
                )
            )

        if case.project_id != domain_binding.project_id:
            issues.append(
                CaseValidationIssue(
                    code="PROJECT_MISMATCH",
                    message=(
                        f"Case project_id '{case.project_id}' does not match "
                        f"domain binding project_id '{domain_binding.project_id}'."
                    ),
                    field="project_id",
                    blocking=True,
                )
            )

        if case.domain_id != domain_binding.domain_id:
            issues.append(
                CaseValidationIssue(
                    code="DOMAIN_MISMATCH",
                    message=(
                        f"Case domain_id '{case.domain_id}' does not match "
                        f"domain binding domain_id '{domain_binding.domain_id}'."
                    ),
                    field="domain_id",
                    blocking=True,
                )
            )

        # 2. Target contract must be ACCEPTED
        if contract.lifecycle_status != ContractLifecycleStatus.ACCEPTED:
            issues.append(
                CaseValidationIssue(
                    code="CONTRACT_NOT_ACCEPTED",
                    message=(
                        f"Target contract '{contract.contract_id}' (v{contract.version}) is in "
                        f"'{contract.lifecycle_status}' status. Only ACCEPTED contracts can be targeted."
                    ),
                    field="contract_id",
                    blocking=True,
                )
            )

        # 3. Contract ID and version agreement
        if (
            case.contract_id != contract.contract_id
            or case.contract_version != contract.version
        ):
            issues.append(
                CaseValidationIssue(
                    code="CONTRACT_VERSION_MISMATCH",
                    message=(
                        f"Case references contract '{case.contract_id}' v{case.contract_version}, "
                        f"but provided contract is '{contract.contract_id}' v{contract.version}."
                    ),
                    field="contract_version",
                    blocking=True,
                )
            )

        # 4. Target rules and versions existence in contract
        contract_rules_map = {r.rule_id: r for r in contract.rules}
        for target_rule_id in case.target_rule_ids:
            rule = contract_rules_map.get(target_rule_id)
            if not rule:
                issues.append(
                    CaseValidationIssue(
                        code="RULE_NOT_FOUND",
                        message=f"Target rule '{target_rule_id}' not found in contract '{contract.contract_id}'.",
                        field="target_rule_ids",
                        blocking=True,
                    )
                )
                continue

            expected_rule_ver = case.target_rule_versions.get(target_rule_id)
            if expected_rule_ver is not None and expected_rule_ver != rule.rule_version:
                issues.append(
                    CaseValidationIssue(
                        code="RULE_VERSION_MISMATCH",
                        message=(
                            f"Rule '{target_rule_id}' version mismatch: case expects v{expected_rule_ver}, "
                            f"contract defines v{rule.rule_version}."
                        ),
                        field="target_rule_versions",
                        blocking=True,
                    )
                )

            # 5. Supported policy family and boundary agreement
            if rule.family not in (
                PolicyFamily.AUTHORIZATION,
                PolicyFamily.CONFIDENTIALITY,
                PolicyFamily.INSTRUCTION_AUTHORITY,
            ):
                issues.append(
                    CaseValidationIssue(
                        code="UNSUPPORTED_FAMILY",
                        message=f"Policy family '{rule.family}' is not supported for test execution.",
                        field="target_rule_ids",
                        blocking=True,
                    )
                )

            if rule.evaluation_boundary != case.planned_evaluation_boundary:
                issues.append(
                    CaseValidationIssue(
                        code="BOUNDARY_MISMATCH",
                        message=(
                            f"Planned evaluation boundary '{case.planned_evaluation_boundary}' "
                            f"does not match rule declared boundary '{rule.evaluation_boundary}'."
                        ),
                        field="planned_evaluation_boundary",
                        blocking=True,
                    )
                )

            # 6. Tool / action mapping and schema compatibility
            tool_mapping = domain_binding.get_tool_for_action(
                rule.action_selector.action
            )
            if not tool_mapping:
                issues.append(
                    CaseValidationIssue(
                        code="TOOL_MAPPING_MISSING",
                        message=f"No tool mapping found for action '{rule.action_selector.action}'.",
                        field="target_rule_ids",
                        blocking=True,
                    )
                )

            # 7. Resource definition existence
            resource_def = domain_binding.get_resource(
                rule.resource_selector.resource_type
            )
            if not resource_def:
                issues.append(
                    CaseValidationIssue(
                        code="RESOURCE_DEFINITION_MISSING",
                        message=f"No resource definition found for '{rule.resource_selector.resource_type}'.",
                        field="target_rule_ids",
                        blocking=True,
                    )
                )

            # 8. Principal role consistency
            if rule.principal_selector.role:
                role_def = domain_binding.get_role(rule.principal_selector.role)
                if not role_def:
                    issues.append(
                        CaseValidationIssue(
                            code="ROLE_DEFINITION_MISSING",
                            message=f"No role definition found for '{rule.principal_selector.role}'.",
                            field="target_rule_ids",
                            blocking=True,
                        )
                    )

        # 9. Required evidence versus declared capabilities
        for req_ev in case.required_evidence:
            base_ev = req_ev.split(".")[0]
            if (
                base_ev not in domain_binding.declared_capabilities
                and req_ev not in domain_binding.declared_capabilities
            ):
                issues.append(
                    CaseValidationIssue(
                        code="CAPABILITY_MISSING",
                        message=f"Required evidence '{req_ev}' is not supported by declared adapter capabilities.",
                        field="required_evidence",
                        blocking=True,
                    )
                )

        # 10. Injection placement and trust tier
        if case.injection_placement:
            placement = case.injection_placement
            if placement.trust_classification not in (
                TrustClassification.UNTRUSTED_CONTENT,
                TrustClassification.UNTRUSTED_EXTERNAL,
            ):
                issues.append(
                    CaseValidationIssue(
                        code="INVALID_INJECTION_TRUST",
                        message=(
                            f"Injection placement trust tier must be untrusted, "
                            f"got '{placement.trust_classification}'."
                        ),
                        field="injection_placement.trust_classification",
                        blocking=True,
                    )
                )

            # Check placement source existence in domain binding
            untrusted_def = domain_binding.get_untrusted_source(placement.source_type)
            if not untrusted_def:
                issues.append(
                    CaseValidationIssue(
                        code="UNTRUSTED_SOURCE_MISSING",
                        message=f"No untrusted source declared in binding for '{placement.source_type}'.",
                        field="injection_placement.source_type",
                        blocking=True,
                    )
                )

        # 11. Separation of attacker goal from legitimate task prompt
        if case.evaluator_bundle.attacker_objective:
            obj = case.evaluator_bundle.attacker_objective.strip()
            if obj and obj.lower() in case.agent_task_prompt.lower():
                issues.append(
                    CaseValidationIssue(
                        code="ORACLE_LEAK_IN_PROMPT",
                        message="Attacker objective text leaked into agent-facing task prompt.",
                        field="agent_task_prompt",
                        blocking=True,
                    )
                )

        # 12. Verification of agent export decoupling
        agent_export = case.build_agent_facing_payload()
        if hasattr(agent_export, "evaluator_bundle"):
            issues.append(
                CaseValidationIssue(
                    code="EVALUATOR_LEAK",
                    message="Agent-facing export illegally exposes evaluator_bundle.",
                    field="agent_facing_payload",
                    blocking=True,
                )
            )

        # Update case state
        case.readiness_issues = issues
        blocking_issues = [i for i in issues if i.blocking]

        if not blocking_issues:
            case.lifecycle_status = TestCaseLifecycleStatus.VALIDATED
        else:
            case.lifecycle_status = TestCaseLifecycleStatus.REJECTED

        # Refresh content hash
        case.content_hash = case.compute_content_hash()
        return case

    def validate_batch(
        self,
        cases: list[GeneratedTestCase],
        contract: PolicyContract,
        domain_binding: DomainBinding,
    ) -> list[GeneratedTestCase]:
        """Validate an entire batch of generated cases."""
        validated_cases: list[GeneratedTestCase] = []
        for case in cases:
            validated = self.validate_case(case, contract, domain_binding)
            validated_cases.append(validated)
        return validated_cases

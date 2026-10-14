"""Candidate policy derivation and extraction implementations for Phase 1."""

import json
import re
from typing import Any
from app.components.c4_policy_aware_safety.contracts.artifacts import ArtifactVersion
from app.components.c4_policy_aware_safety.contracts.findings import Severity
from app.components.c4_policy_aware_safety.contracts.integration import (
    BasePolicyExtractor,
)
from app.components.c4_policy_aware_safety.contracts.policy import (
    ActionSelector,
    EvaluationBoundary,
    PolicyFamily,
    PolicyRequirement,
    PolicyRule,
    PrincipalSelector,
    ResourceSelector,
    RuleLifecycleStatus,
)
from app.components.c4_policy_aware_safety.contracts.predicates import (
    AtomicPredicate,
    PredicateOperator,
)
from app.components.c4_policy_aware_safety.contracts.sources import (
    SourceReference,
    TextSpan,
)
from app.components.c4_policy_aware_safety.derivation.issues import (
    CandidateValidationIssue,
    IssueCode,
)


class StructuredPolicyImporter(BasePolicyExtractor):
    """
    Importer for explicit structured JSON policy definitions.
    Strictly validates schema, maps fields to PolicyRule models, and enforces source provenance.
    """

    def extract_candidates(self, artifact: ArtifactVersion) -> list[PolicyRule]:
        """Import structured rules from normalized JSON artifact content."""
        try:
            data = json.loads(artifact.normalized_content)
        except json.JSONDecodeError as err:
            raise ValueError(
                f"Artifact {artifact.artifact_id} does not contain valid JSON: {err}"
            ) from err

        raw_rules = data if isinstance(data, list) else data.get("rules", [])
        candidate_rules: list[PolicyRule] = []

        for idx, item in enumerate(raw_rules):
            # If item lacks source references, automatically attach provenance pointing to this artifact
            if "sources" not in item or not item["sources"]:
                item["sources"] = [
                    {
                        "artifact_id": artifact.artifact_id,
                        "artifact_version": artifact.version,
                        "section_id": "json-root",
                        "supporting_excerpt": json.dumps(item),
                    }
                ]

            rule = PolicyRule.model_validate(item)
            # Ensure candidate lifecycle status
            rule.status = RuleLifecycleStatus.CANDIDATE
            candidate_rules.append(rule)

        return candidate_rules


class ControlledLanguageExtractor(BasePolicyExtractor):
    """
    Deterministic extractor for a strictly documented subset of controlled-language patterns.
    Retains exact source character spans and excerpts.
    Explicitly flags or rejects wording outside supported patterns.
    """

    # Pattern 1: Role <ROLE> must not <ACTION> <RESOURCE> where <FIELD> <OP> <VALUE>.
    # Example: "Role CUSTOMER_SUPPORT must not issue_refund orders where amount > 5000."
    _DENY_PATTERN = re.compile(
        r"Role\s+([A-Za-z0-9_-]+)\s+must\s+not\s+([a-z0-9_]+)\s+([a-z0-9_]+)"
        r"(?:\s+where\s+([a-zA-Z0-9_.]+)\s*(==|!=|<=|>=|<|>)\s*([0-9]+|\"[^\"]+\"))?\.",
        re.IGNORECASE,
    )

    # Pattern 2: Role <ROLE> requires approval from <APPROVER_ROLE> to <ACTION> <RESOURCE> where <FIELD> <OP> <VALUE>.
    # Example: "Role CUSTOMER_SUPPORT requires approval from MANAGER to issue_refund orders where amount > 5000."
    _REQUIRE_APPROVAL_PATTERN = re.compile(
        r"Role\s+([A-Za-z0-9_-]+)\s+requires\s+approval\s+from\s+([A-Za-z0-9_-]+)\s+to\s+([a-z0-9_]+)\s+([a-z0-9_]+)"
        r"(?:\s+where\s+([a-zA-Z0-9_.]+)\s*(==|!=|<=|>=|<|>)\s*([0-9]+|\"[^\"]+\"))?\.",
        re.IGNORECASE,
    )

    # Pattern 3: Role <ROLE> is prohibited from disclosing <RESOURCE> to <RECIPIENT>.
    # Example: "Role CUSTOMER_SUPPORT is prohibited from disclosing customer_pii to external_untrusted."
    _CONFIDENTIALITY_PATTERN = re.compile(
        r"Role\s+([A-Za-z0-9_-]+)\s+is\s+prohibited\s+from\s+disclosing\s+([a-z0-9_]+)\s+to\s+([A-Za-z0-9_-]+)\.",
        re.IGNORECASE,
    )

    _OP_MAP = {
        "==": PredicateOperator.EQ,
        "!=": PredicateOperator.NEQ,
        "<": PredicateOperator.LT,
        "<=": PredicateOperator.LTE,
        ">": PredicateOperator.GT,
        ">=": PredicateOperator.GTE,
    }

    def _parse_value(self, val_str: str) -> Any:
        if val_str.isdigit():
            return int(val_str)
        if val_str.startswith('"') and val_str.endswith('"'):
            return val_str[1:-1]
        return val_str

    def extract_candidates_with_issues(
        self,
        artifact: ArtifactVersion,
    ) -> tuple[list[PolicyRule], list[CandidateValidationIssue]]:
        """
        Extract rules from sentences. For recognized controlled-language patterns,
        construct PolicyRule with exact source spans.
        For sentences starting with 'Role ' that deviate from supported syntax,
        generate UNSUPPORTED or AMBIGUOUS candidate issues.
        """
        text = artifact.normalized_content
        rules: list[PolicyRule] = []
        issues: list[CandidateValidationIssue] = []

        # Sentence tokenizer split on periods followed by space or newline
        sentence_matches = list(re.finditer(r"([A-Z][^\.\n]*\.)", text))

        for idx, s_match in enumerate(sentence_matches):
            sentence = s_match.group(1).strip()
            start_char = s_match.start()
            end_char = s_match.end()

            # Pattern 1: Deny action
            m1 = self._DENY_PATTERN.match(sentence)
            if m1:
                role, action, resource, field, op_str, val_str = m1.groups()
                rule_id = f"rule-{artifact.artifact_id}-{idx + 1}"

                applicability = None
                if field and op_str and val_str:
                    op = self._OP_MAP[op_str]
                    parsed_val = self._parse_value(val_str)
                    applicability = AtomicPredicate(
                        field=field, operator=op, value=parsed_val
                    )

                source_ref = SourceReference(
                    artifact_id=artifact.artifact_id,
                    artifact_version=artifact.version,
                    text_span=TextSpan(start_char=start_char, end_char=end_char),
                    supporting_excerpt=sentence,
                )

                rule = PolicyRule(
                    rule_id=rule_id,
                    rule_version=1,
                    family=PolicyFamily.AUTHORIZATION,
                    description=f"Deny {role} performing {action} on {resource}",
                    principal_selector=PrincipalSelector(role=role.upper()),
                    action_selector=ActionSelector(action=action),
                    resource_selector=ResourceSelector(resource_type=resource),
                    applicability=applicability,
                    requirement=PolicyRequirement.DENY,
                    evaluation_boundary=EvaluationBoundary.ATTEMPTED_ACTION,
                    required_evidence=["principal.role", "action.action_id"],
                    severity=Severity.HIGH,
                    sources=[source_ref],
                    status=RuleLifecycleStatus.CANDIDATE,
                )
                rules.append(rule)
                continue

            # Pattern 2: Require approval
            m2 = self._REQUIRE_APPROVAL_PATTERN.match(sentence)
            if m2:
                role, approver_role, action, resource, field, op_str, val_str = (
                    m2.groups()
                )
                rule_id = f"rule-{artifact.artifact_id}-{idx + 1}"

                applicability = None
                if field and op_str and val_str:
                    op = self._OP_MAP[op_str]
                    parsed_val = self._parse_value(val_str)
                    applicability = AtomicPredicate(
                        field=field, operator=op, value=parsed_val
                    )

                source_ref = SourceReference(
                    artifact_id=artifact.artifact_id,
                    artifact_version=artifact.version,
                    text_span=TextSpan(start_char=start_char, end_char=end_char),
                    supporting_excerpt=sentence,
                )

                # Compliance condition requires valid approval from approver_role
                compliance_condition = AtomicPredicate(
                    field="approval.approved",
                    operator=PredicateOperator.EQ,
                    value=True,
                )

                rule = PolicyRule(
                    rule_id=rule_id,
                    rule_version=1,
                    family=PolicyFamily.AUTHORIZATION,
                    description=f"{role} requires {approver_role} approval for {action} on {resource}",
                    principal_selector=PrincipalSelector(role=role.upper()),
                    action_selector=ActionSelector(action=action),
                    resource_selector=ResourceSelector(resource_type=resource),
                    applicability=applicability,
                    requirement=PolicyRequirement.REQUIRE,
                    compliance_condition=compliance_condition,
                    evaluation_boundary=EvaluationBoundary.ATTEMPTED_ACTION,
                    required_evidence=[
                        "principal.role",
                        "action.action_id",
                        "approval.approved",
                    ],
                    severity=Severity.HIGH,
                    sources=[source_ref],
                    status=RuleLifecycleStatus.CANDIDATE,
                    acceptance_metadata={
                        "required_approver_role": approver_role.upper()
                    },
                )
                rules.append(rule)
                continue

            # Pattern 3: Confidentiality prohibition
            m3 = self._CONFIDENTIALITY_PATTERN.match(sentence)
            if m3:
                role, resource, recipient = m3.groups()
                rule_id = f"rule-{artifact.artifact_id}-{idx + 1}"

                source_ref = SourceReference(
                    artifact_id=artifact.artifact_id,
                    artifact_version=artifact.version,
                    text_span=TextSpan(start_char=start_char, end_char=end_char),
                    supporting_excerpt=sentence,
                )

                rule = PolicyRule(
                    rule_id=rule_id,
                    rule_version=1,
                    family=PolicyFamily.CONFIDENTIALITY,
                    description=f"{role} prohibited from disclosing {resource} to {recipient}",
                    principal_selector=PrincipalSelector(role=role.upper()),
                    action_selector=ActionSelector(action="disclose"),
                    resource_selector=ResourceSelector(resource_type=resource),
                    requirement=PolicyRequirement.DENY,
                    evaluation_boundary=EvaluationBoundary.OUTPUT_DISCLOSURE,
                    required_evidence=["disclosures"],
                    severity=Severity.HIGH,
                    sources=[source_ref],
                    status=RuleLifecycleStatus.CANDIDATE,
                    acceptance_metadata={"prohibited_recipient": recipient},
                )
                rules.append(rule)
                continue

            # Check if sentence looks like a policy statement but violates controlled grammar
            if (
                sentence.lower().startswith("role ")
                or "must not" in sentence.lower()
                or "requires" in sentence.lower()
            ):
                issues.append(
                    CandidateValidationIssue(
                        code=IssueCode.UNSUPPORTED,
                        message=(
                            f"Sentence at [{start_char}:{end_char}] ('{sentence}') "
                            "uses phrasing outside the supported controlled-language grammar."
                        ),
                        field="normalized_content",
                        blocking=True,
                    )
                )

        return rules, issues

    def extract_candidates(self, artifact: ArtifactVersion) -> list[PolicyRule]:
        rules, _ = self.extract_candidates_with_issues(artifact)
        return rules

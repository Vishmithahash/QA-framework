"""Unit tests for C4 artifact intake and candidate rule derivation."""

from app.components.c4_policy_aware_safety.contracts.artifacts import ArtifactKind
from app.components.c4_policy_aware_safety.contracts.policy import (
    EvaluationBoundary,
    PolicyFamily,
    PolicyRequirement,
    RuleLifecycleStatus,
)
from app.components.c4_policy_aware_safety.derivation.extractor import (
    ControlledLanguageExtractor,
    StructuredPolicyImporter,
)
from app.components.c4_policy_aware_safety.derivation.issues import IssueCode
from app.components.c4_policy_aware_safety.intake.artifact_service import (
    ArtifactIntakeService,
)


def test_text_artifact_registration_and_sections():
    """Verify text artifact intake, content hashing, and section offset parsing."""
    service = ArtifactIntakeService()
    raw_markdown = """# Global Security Policy

## Section 1: Refund Controls
Role CUSTOMER_SUPPORT must not issue_refund orders where amount > 5000.

## Section 2: PII Disclosure
Role CUSTOMER_SUPPORT is prohibited from disclosing customer_pii to external_untrusted.
"""
    artifact = service.register_text_artifact(
        project_id="proj-alpha",
        artifact_id="art-policy-doc",
        version="1.0.0",
        kind=ArtifactKind.POLICY_DOCUMENT,
        raw_text=raw_markdown,
    )

    assert artifact.project_id == "proj-alpha"
    assert artifact.artifact_id == "art-policy-doc"
    assert artifact.version == "1.0.0"
    assert len(artifact.content_hash) == 64
    assert len(artifact.sections) >= 2

    sec1 = [s for s in artifact.sections if "refund-controls" in s.section_id][0]
    assert sec1.title == "Section 1: Refund Controls"
    assert "Role CUSTOMER_SUPPORT must not" in sec1.content


def test_structured_json_policy_import():
    """Verify structured JSON policy import attaches provenance and candidate status."""
    service = ArtifactIntakeService()
    json_rules = [
        {
            "rule_id": "rule-refund-limit",
            "rule_version": 1,
            "family": "AUTHORIZATION",
            "action_selector": {"action": "issue_refund"},
            "resource_selector": {"resource_type": "orders"},
            "principal_selector": {"role": "CUSTOMER_SUPPORT"},
            "requirement": "DENY",
            "evaluation_boundary": "ATTEMPTED_ACTION",
            "required_evidence": ["action_attempt", "principal.role"],
            "severity": "HIGH",
            "sources": [
                {
                    "artifact_id": "art-structured-1",
                    "artifact_version": "1.0.0",
                    "supporting_excerpt": "Deny refund without manager approval",
                }
            ],
        }
    ]

    artifact = service.register_json_artifact(
        project_id="proj-alpha",
        artifact_id="art-structured-1",
        version="1.0.0",
        kind=ArtifactKind.REQUIREMENTS,
        json_data=json_rules,
    )

    importer = StructuredPolicyImporter()
    candidates = importer.extract_candidates(artifact)

    assert len(candidates) == 1
    assert candidates[0].rule_id == "rule-refund-limit"
    assert candidates[0].status == RuleLifecycleStatus.CANDIDATE
    assert candidates[0].family == PolicyFamily.AUTHORIZATION


def test_controlled_language_extraction_exact_spans():
    """Verify controlled language extraction captures exact source spans and excerpts."""
    service = ArtifactIntakeService()
    text = (
        "Role CUSTOMER_SUPPORT requires approval from MANAGER to issue_refund orders where amount > 5000. "
        "Role CUSTOMER_SUPPORT is prohibited from disclosing canary_secret to external_customer."
    )
    artifact = service.register_text_artifact(
        project_id="proj-alpha",
        artifact_id="art-cl-doc",
        version="1.0.0",
        kind=ArtifactKind.POLICY_DOCUMENT,
        raw_text=text,
    )

    extractor = ControlledLanguageExtractor()
    rules, issues = extractor.extract_candidates_with_issues(artifact)

    assert len(rules) == 2
    assert len(issues) == 0

    r1 = rules[0]
    assert r1.family == PolicyFamily.AUTHORIZATION
    assert r1.requirement == PolicyRequirement.REQUIRE
    assert r1.evaluation_boundary == EvaluationBoundary.ATTEMPTED_ACTION
    assert r1.principal_selector.role == "CUSTOMER_SUPPORT"
    assert r1.action_selector.action == "issue_refund"
    assert r1.resource_selector.resource_type == "orders"
    assert len(r1.sources) == 1

    # Verify source span points directly to original text
    span = r1.sources[0].text_span
    assert span is not None
    extracted_text = artifact.normalized_content[
        span.start_char : span.end_char
    ].strip()
    assert extracted_text == r1.sources[0].supporting_excerpt.strip()

    r2 = rules[1]
    assert r2.family == PolicyFamily.CONFIDENTIALITY
    assert r2.evaluation_boundary == EvaluationBoundary.OUTPUT_DISCLOSURE


def test_controlled_language_flags_unsupported_phrasing():
    """Wording outside supported controlled-language grammar must produce UNSUPPORTED candidate issue."""
    service = ArtifactIntakeService()
    # Sentence starts with Role, but has free-form unparsed phrasing
    text = "Role CUSTOMER_SUPPORT may possibly execute anything unless supervisor says otherwise."
    artifact = service.register_text_artifact(
        project_id="proj-alpha",
        artifact_id="art-freeform",
        version="1.0.0",
        kind=ArtifactKind.POLICY_DOCUMENT,
        raw_text=text,
    )

    extractor = ControlledLanguageExtractor()
    rules, issues = extractor.extract_candidates_with_issues(artifact)

    assert len(rules) == 0
    assert len(issues) >= 1
    assert issues[0].code == IssueCode.UNSUPPORTED
    assert issues[0].blocking is True

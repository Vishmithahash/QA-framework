"""Validation logic for CandidateTestCase definitions (FR-02/FR-03)."""

from typing import Optional
from ..contracts.candidate_case import (
    CandidateTestCase,
    ConstraintOperator,
    ConstraintType,
    ValidationIssue,
)
from ..contracts.project_input import ProjectInput
from .issue_codes import IssueCode
from .schema_validator import validate_instance_against_schema


def validate_candidate_case(
    candidate: CandidateTestCase,
    project_input: Optional[ProjectInput] = None,
) -> list[ValidationIssue]:
    """Validate candidate test expectations before execution eligibility."""
    issues: list[ValidationIssue] = []

    # 1. Basic Identifiers
    if not candidate.case_id or not candidate.case_id.strip():
        issues.append(
            ValidationIssue(
                code=IssueCode.MISSING_CASE_ID.value,
                field_path="case_id",
                message="Test case identifier must not be empty.",
            )
        )

    if not candidate.task_prompt or not candidate.task_prompt.strip():
        issues.append(
            ValidationIssue(
                code=IssueCode.MISSING_TASK_PROMPT.value,
                field_path="task_prompt",
                message="Task prompt presented to agent must not be empty.",
            )
        )

    # 2. Project consistency
    tool_map = {}
    known_req_ids = set()
    if project_input:
        if candidate.project_id != project_input.project_id:
            issues.append(
                ValidationIssue(
                    code=IssueCode.PROJECT_ID_MISMATCH.value,
                    field_path="project_id",
                    message=f"Candidate project_id '{candidate.project_id}' does not match project '{project_input.project_id}'.",
                )
            )

        tool_map = {t.tool_name: t for t in project_input.tools}
        known_req_ids = {r.req_id for r in project_input.requirements}

        # Check requirement versions references
        for req_id in candidate.requirement_versions:
            if req_id not in known_req_ids:
                issues.append(
                    ValidationIssue(
                        code=IssueCode.UNRESOLVED_REQUIREMENT_REF.value,
                        field_path=f"requirement_versions['{req_id}']",
                        message=f"Candidate references requirement '{req_id}' not found in project specification.",
                    )
                )

    # 3. Expected Calls Structure
    if not candidate.expected_calls:
        issues.append(
            ValidationIssue(
                code=IssueCode.EMPTY_EXPECTED_CALLS.value,
                field_path="expected_calls",
                message="Candidate test case defines no expected tool call constraints.",
                severity="WARNING",
            )
        )

    uses_fixture_facts = False

    for i, call in enumerate(candidate.expected_calls):
        prefix = f"expected_calls[{i}]"

        # Check tool registration in project
        tool_def = tool_map.get(call.tool_name)
        if project_input and not tool_def:
            issues.append(
                ValidationIssue(
                    code=IssueCode.UNKNOWN_TOOL_NAME.value,
                    field_path=f"{prefix}.tool_name",
                    message=f"Expected tool '{call.tool_name}' is not registered in project tools.",
                )
            )

        # Check call requirement references
        if project_input:
            for req_ref in call.requirement_refs:
                if req_ref not in known_req_ids:
                    issues.append(
                        ValidationIssue(
                            code=IssueCode.UNRESOLVED_REQUIREMENT_REF.value,
                            field_path=f"{prefix}.requirement_refs",
                            message=f"Expected call references undefined requirement '{req_ref}'.",
                        )
                    )

        # Validate argument constraints
        for param_name, constraint in call.argument_constraints.items():
            param_prefix = f"{prefix}.argument_constraints['{param_name}']"

            # Check for unsupported assertion forms
            if constraint.constraint_type == ConstraintType.UNSUPPORTED:
                issues.append(
                    ValidationIssue(
                        code=IssueCode.UNSUPPORTED_ASSERTION_FORM.value,
                        field_path=f"{param_prefix}.constraint_type",
                        message=f"Parameter '{param_name}' uses unsupported or arbitrary expression assertion: '{constraint.raw_expression}'.",
                    )
                )

            # Check if fixture fact is used
            if constraint.constraint_type == ConstraintType.FIXTURE_FACT:
                uses_fixture_facts = True
                if not constraint.reference_path:
                    issues.append(
                        ValidationIssue(
                            code=IssueCode.UNSUPPORTED_ASSERTION_FORM.value,
                            field_path=f"{param_prefix}.reference_path",
                            message=f"Fixture fact constraint on '{param_name}' is missing reference_path.",
                        )
                    )

            # Check for provable contradictions
            if (
                constraint.operator == ConstraintOperator.IS_NULL
                and constraint.operator == ConstraintOperator.NOT_NULL
            ):
                issues.append(
                    ValidationIssue(
                        code=IssueCode.CONTRADICTORY_CONSTRAINTS.value,
                        field_path=f"{param_prefix}",
                        message=f"Contradictory nullability constraint on parameter '{param_name}'.",
                    )
                )

            if (
                constraint.operator == ConstraintOperator.IS_NULL
                and constraint.literal_value is not None
            ):
                issues.append(
                    ValidationIssue(
                        code=IssueCode.CONTRADICTORY_CONSTRAINTS.value,
                        field_path=f"{param_prefix}",
                        message=f"Contradictory constraint on '{param_name}': operator IS_NULL with non-null literal value.",
                    )
                )

            # Validate literal values against tool schema
            if (
                tool_def
                and constraint.constraint_type == ConstraintType.LITERAL
                and constraint.operator
                in (ConstraintOperator.EQUALS, ConstraintOperator.IN_SET)
                and constraint.literal_value is not None
            ):
                param_schema = tool_def.parameters_schema.get("properties", {}).get(
                    param_name
                )
                if param_schema:
                    # Construct an object matching the schema for validation
                    schema_to_test = {
                        "type": "object",
                        "properties": {param_name: param_schema},
                        "required": [param_name],
                    }
                    instance_to_test = {param_name: constraint.literal_value}
                    schema_errors = validate_instance_against_schema(
                        instance_to_test, schema_to_test
                    )
                    if schema_errors:
                        issues.append(
                            ValidationIssue(
                                code=IssueCode.EXPECTED_VALUE_SCHEMA_VIOLATION.value,
                                field_path=f"{param_prefix}.literal_value",
                                message=f"Expected value for '{param_name}' violates tool parameter schema: {'; '.join(schema_errors)}",
                            )
                        )

    # 4. Fixture references check
    if uses_fixture_facts and not candidate.fixture_refs:
        issues.append(
            ValidationIssue(
                code=IssueCode.MISSING_FIXTURE_REFS.value,
                field_path="fixture_refs",
                message="Candidate uses FIXTURE_FACT constraints but specifies no fixture_refs.",
            )
        )

    # 5. Required evidence references check
    if not candidate.required_evidence_refs:
        issues.append(
            ValidationIssue(
                code=IssueCode.MISSING_EVIDENCE_REFS.value,
                field_path="required_evidence_refs",
                message="Candidate test case requires at least one evidence reference specification (e.g. 'trace:tool_calls').",
                severity="WARNING",
            )
        )

    return issues

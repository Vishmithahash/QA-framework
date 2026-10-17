"""Validation logic for ProjectInput bundles (FR-01)."""

from ..contracts.candidate_case import ValidationIssue
from ..contracts.project_input import ProjectInput
from .issue_codes import IssueCode
from .schema_validator import validate_schema_structure


def validate_project_input(project_input: ProjectInput) -> list[ValidationIssue]:
    """Validate project intake configuration and tool definitions."""
    issues: list[ValidationIssue] = []

    # 1. Project Identifier and Domain
    if not project_input.project_id or not project_input.project_id.strip():
        issues.append(
            ValidationIssue(
                code=IssueCode.MISSING_PROJECT_ID.value,
                field_path="project_id",
                message="Project identifier must not be empty.",
            )
        )

    if not project_input.domain or not project_input.domain.strip():
        issues.append(
            ValidationIssue(
                code=IssueCode.MISSING_DOMAIN.value,
                field_path="domain",
                message="Project domain must not be empty.",
            )
        )

    # 2. Known Requirement IDs
    known_req_ids = {r.req_id for r in project_input.requirements if r.req_id}

    # 3. Duplicate Tool IDs and Names
    seen_tool_ids: set[str] = set()
    seen_tool_names: set[str] = set()

    for i, tool in enumerate(project_input.tools):
        prefix = f"tools[{i}]"

        if tool.tool_id in seen_tool_ids:
            issues.append(
                ValidationIssue(
                    code=IssueCode.DUPLICATE_TOOL_ID.value,
                    field_path=f"{prefix}.tool_id",
                    message=f"Duplicate tool identifier '{tool.tool_id}' detected.",
                )
            )
        else:
            seen_tool_ids.add(tool.tool_id)

        if tool.tool_name in seen_tool_names:
            issues.append(
                ValidationIssue(
                    code=IssueCode.DUPLICATE_TOOL_NAME.value,
                    field_path=f"{prefix}.tool_name",
                    message=f"Duplicate tool name '{tool.tool_name}' detected.",
                )
            )
        else:
            seen_tool_names.add(tool.tool_name)

        # 4. JSON Schema Validation of Tool Parameters
        param_schema_err = validate_schema_structure(tool.parameters_schema)
        if param_schema_err:
            issues.append(
                ValidationIssue(
                    code=IssueCode.INVALID_PARAMETERS_SCHEMA.value,
                    field_path=f"{prefix}.parameters_schema",
                    message=f"Tool '{tool.tool_name}' has invalid parameters JSON Schema: {param_schema_err}",
                )
            )
        else:
            # Ensure top-level parameters schema represents an object
            schema_type = tool.parameters_schema.get("type")
            if schema_type != "object" and "properties" not in tool.parameters_schema:
                issues.append(
                    ValidationIssue(
                        code=IssueCode.INVALID_PARAMETERS_SCHEMA.value,
                        field_path=f"{prefix}.parameters_schema.type",
                        message=f"Tool '{tool.tool_name}' parameters schema must be an object type.",
                    )
                )

        # 5. Output Schema Validation (if provided)
        if tool.output_schema is not None:
            output_schema_err = validate_schema_structure(tool.output_schema)
            if output_schema_err:
                issues.append(
                    ValidationIssue(
                        code=IssueCode.INVALID_OUTPUT_SCHEMA.value,
                        field_path=f"{prefix}.output_schema",
                        message=f"Tool '{tool.tool_name}' has invalid output JSON Schema: {output_schema_err}",
                    )
                )

        # 6. Requirement References Integrity
        for req_ref in tool.requirement_refs:
            if req_ref not in known_req_ids:
                issues.append(
                    ValidationIssue(
                        code=IssueCode.UNRESOLVED_REQUIREMENT_REF.value,
                        field_path=f"{prefix}.requirement_refs",
                        message=f"Tool '{tool.tool_name}' references undefined requirement '{req_ref}'.",
                    )
                )

    # 7. Tool-to-Code Mapping Integrity
    for j, mapping in enumerate(project_input.tool_code_mappings):
        if mapping.tool_id not in seen_tool_ids:
            issues.append(
                ValidationIssue(
                    code=IssueCode.UNRESOLVED_TOOL_REF.value,
                    field_path=f"tool_code_mappings[{j}].tool_id",
                    message=f"Code mapping references unregistered tool '{mapping.tool_id}'.",
                )
            )

    # 8. Source Code Access Check (Informational Warning)
    if not project_input.source_code_ref:
        issues.append(
            ValidationIssue(
                code=IssueCode.SOURCE_CODE_ACCESS_MISSING.value,
                field_path="source_code_ref",
                message="Source code reference is absent. Tool-call correctness testing is fully supported, but code-level defect localization and diagnosis will be unavailable.",
                severity="WARNING",
            )
        )

    return issues

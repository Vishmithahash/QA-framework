"""Automated tests for Component 1 (C1): Tool-Call Correctness Phase 1.

Verifies:
- Valid inputs and candidate test cases.
- Duplicate tool registration.
- Invalid JSON schemas and unresolved references.
- Candidate expected value violating argument schema.
- Unsupported or contradictory assertion constraints.
- Missing fixture/evidence references.
- Source access optionality for correctness testing.
- Missing evidence vs. explicit null distinction.
- Malformed observed calls remaining recordable in evidence traces.
- Consistent version and project references.
- JSON serialization round trips.
- Synthetic NexaCart task example: 'Show all my paid orders' with getOrders.
"""

from app.components.c1_tool_call_correctness import (
    C1ValidationService,
    CandidateTestCase,
    CaseReadiness,
    ConstraintOperator,
    ConstraintType,
    ExecutionStatus,
    ExecutionTrace,
    ExpectedCallConstraint,
    ObservedToolCall,
    ProjectInput,
    RequirementDefinition,
    ToolCodeMappingReference,
    ToolDefinition,
    ValueConstraint,
)
from app.components.c1_tool_call_correctness.validators.issue_codes import IssueCode


def create_sample_project() -> ProjectInput:
    """Helper creating a valid NexaCart project input bundle."""
    return ProjectInput(
        project_id="J26-SE-341",
        domain="NexaCart / e-commerce",
        requirements=[
            RequirementDefinition(
                req_id="REQ-ORD-01",
                version="1.0.0",
                description="User should be able to view their orders filtered by order status.",
                acceptance_constraints=[
                    "Only permitted statuses: PENDING, PAID, SHIPPED, REFUNDED"
                ],
            ),
            RequirementDefinition(
                req_id="REQ-CUST-01",
                version="1.0.0",
                description="Agent must bind customerId from authenticated session.",
                acceptance_constraints=["customerId must be non-empty string"],
            ),
        ],
        tools=[
            ToolDefinition(
                tool_id="TOOL-ORD-01",
                tool_name="getOrders",
                description="Retrieves orders matching specified customer ID and order status",
                version="1.0.0",
                parameters_schema={
                    "type": "object",
                    "properties": {
                        "customerId": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["PENDING", "PAID", "SHIPPED", "REFUNDED"],
                        },
                    },
                    "required": ["customerId", "status"],
                },
                requirement_refs=["REQ-ORD-01", "REQ-CUST-01"],
            )
        ],
        agent_connection_ref="vault://agents/nexacart-primary",
        fixture_config_ref="fixture://ecom-clean-db-v1",
        source_code_ref="git://internal/nexacart-core#main",
        tool_code_mappings=[
            ToolCodeMappingReference(
                tool_id="TOOL-ORD-01",
                source_file_path="src/tools/order_tools.py",
                symbol_name="get_orders_handler",
                line_start=45,
                line_end=80,
            )
        ],
    )


def create_sample_candidate() -> CandidateTestCase:
    """Helper creating a valid synthetic candidate test case."""
    return CandidateTestCase(
        case_id="TC-C1-001",
        project_id="J26-SE-341",
        task_prompt="Show all my paid orders.",
        fixture_refs=["fixture://ecom-clean-db-v1"],
        requirement_versions={"REQ-ORD-01": "1.0.0", "REQ-CUST-01": "1.0.0"},
        tool_versions={"getOrders": "1.0.0"},
        expected_calls=[
            ExpectedCallConstraint(
                call_key="call_1",
                tool_name="getOrders",
                tool_id="TOOL-ORD-01",
                is_required=True,
                argument_constraints={
                    "customerId": ValueConstraint(
                        constraint_type=ConstraintType.SESSION_FACT,
                        reference_path="authenticated_session.customer_id",
                    ),
                    "status": ValueConstraint(
                        constraint_type=ConstraintType.LITERAL,
                        operator=ConstraintOperator.EQUALS,
                        literal_value="PAID",
                    ),
                },
                requirement_refs=["REQ-ORD-01", "REQ-CUST-01"],
            )
        ],
        required_evidence_refs=["trace://tool_calls/call_1"],
    )


# 1. Test Valid Inputs and Valid Candidate
def test_valid_project_and_candidate():
    service = C1ValidationService()
    project = create_sample_project()
    candidate = create_sample_candidate()

    is_proj_valid, proj_issues = service.validate_project(project)
    assert is_proj_valid is True
    # Filter out warnings (e.g. source access warnings) to ensure zero errors
    errors = [i for i in proj_issues if i.severity == "ERROR"]
    assert len(errors) == 0

    prepared_candidate = service.prepare_and_freeze_candidate(candidate, project)
    assert prepared_candidate.readiness == CaseReadiness.READY
    assert (
        len([i for i in prepared_candidate.validation_issues if i.severity == "ERROR"])
        == 0
    )


# 2. Test Duplicate Tool Registration
def test_duplicate_tool_registration():
    service = C1ValidationService()
    project = create_sample_project()
    # Add a duplicate tool with same tool_id and tool_name
    duplicate_tool = project.tools[0].model_copy()
    project.tools.append(duplicate_tool)

    is_valid, issues = service.validate_project(project)
    assert is_valid is False
    codes = {issue.code for issue in issues}
    assert IssueCode.DUPLICATE_TOOL_ID.value in codes
    assert IssueCode.DUPLICATE_TOOL_NAME.value in codes


# 3. Test Invalid Schemas and Unresolved References
def test_invalid_schemas_and_unresolved_references():
    service = C1ValidationService()
    project = create_sample_project()
    # Set an invalid parameters JSON schema (invalid type specification)
    project.tools[0].parameters_schema = {"type": "invalid_primitive_type"}
    project.tools[0].requirement_refs.append("REQ-NONEXISTENT")

    is_valid, issues = service.validate_project(project)
    assert is_valid is False
    codes = {issue.code for issue in issues}
    assert IssueCode.INVALID_PARAMETERS_SCHEMA.value in codes
    assert IssueCode.UNRESOLVED_REQUIREMENT_REF.value in codes


# 4. Test Candidate Expected Value Violating Argument Schema
def test_candidate_expected_value_violating_argument_schema():
    service = C1ValidationService()
    project = create_sample_project()
    candidate = create_sample_candidate()

    # The schema specifies enum: ["PENDING", "PAID", "SHIPPED", "REFUNDED"].
    # Setting an invalid status literal "INVALID_STATUS_VALUE" violates the schema.
    candidate.expected_calls[0].argument_constraints["status"] = ValueConstraint(
        constraint_type=ConstraintType.LITERAL,
        operator=ConstraintOperator.EQUALS,
        literal_value="INVALID_STATUS_VALUE",
    )

    prepared = service.prepare_and_freeze_candidate(candidate, project)
    assert prepared.readiness == CaseReadiness.NOT_READY
    codes = {issue.code for issue in prepared.validation_issues}
    assert IssueCode.EXPECTED_VALUE_SCHEMA_VIOLATION.value in codes


# 5. Test Unsupported Assertion Form and Contradictory Constraints
def test_unsupported_and_contradictory_constraints():
    service = C1ValidationService()
    project = create_sample_project()
    candidate = create_sample_candidate()

    # 1. Unsupported arbitrary expression
    candidate.expected_calls[0].argument_constraints["customerId"] = ValueConstraint(
        constraint_type=ConstraintType.UNSUPPORTED,
        raw_expression="SELECT customer_id FROM database WHERE id=27",
    )

    # 2. Contradictory constraint: IS_NULL with literal value
    candidate.expected_calls[0].argument_constraints["status"] = ValueConstraint(
        constraint_type=ConstraintType.LITERAL,
        operator=ConstraintOperator.IS_NULL,
        literal_value="PAID",
    )

    prepared = service.prepare_and_freeze_candidate(candidate, project)
    assert prepared.readiness == CaseReadiness.NOT_READY
    codes = {issue.code for issue in prepared.validation_issues}
    assert IssueCode.UNSUPPORTED_ASSERTION_FORM.value in codes
    assert IssueCode.CONTRADICTORY_CONSTRAINTS.value in codes


# 6. Test Missing Fixture References
def test_missing_fixture_references_when_fixture_fact_used():
    service = C1ValidationService()
    project = create_sample_project()
    candidate = create_sample_candidate()

    # Use FIXTURE_FACT but clear fixture_refs
    candidate.fixture_refs = []
    candidate.expected_calls[0].argument_constraints["customerId"] = ValueConstraint(
        constraint_type=ConstraintType.FIXTURE_FACT,
        reference_path="customers.0.id",
    )

    prepared = service.prepare_and_freeze_candidate(candidate, project)
    assert prepared.readiness == CaseReadiness.NOT_READY
    codes = {issue.code for issue in prepared.validation_issues}
    assert IssueCode.MISSING_FIXTURE_REFS.value in codes


# 7. Test Source Code Access Being Optional for Correctness Testing
def test_source_code_access_optional_for_correctness():
    service = C1ValidationService()
    project = create_sample_project()
    project.source_code_ref = None  # No source code access
    project.tool_code_mappings = []

    is_valid, issues = service.validate_project(project)
    # Must still be valid! (WARNING, not ERROR)
    assert is_valid is True
    warning_codes = {i.code for i in issues if i.severity == "WARNING"}
    assert IssueCode.SOURCE_CODE_ACCESS_MISSING.value in warning_codes

    candidate = create_sample_candidate()
    prepared = service.prepare_and_freeze_candidate(candidate, project)
    # Readiness is READY even without source access
    assert prepared.readiness == CaseReadiness.READY


# 8. Test Missing Evidence vs. Explicit Null Distinction
def test_missing_evidence_vs_explicit_null():
    call_missing_output = ObservedToolCall(
        call_id="call-001",
        event_id="evt-001",
        tool_name="getOrders",
        output=None,
        output_is_explicit_null=False,
    )

    call_explicit_null = ObservedToolCall(
        call_id="call-002",
        event_id="evt-002",
        tool_name="getOrders",
        output=None,
        output_is_explicit_null=True,
    )

    assert call_missing_output.output is None
    assert call_missing_output.output_is_explicit_null is False

    assert call_explicit_null.output is None
    assert call_explicit_null.output_is_explicit_null is True


# 9. Test Malformed Observed Calls Remaining Recordable
def test_malformed_observed_calls_recordable():
    # Synthetic example from proposal: Agent invoked getOrders with status 'REFUNDED'
    # instead of expected 'PAID', or with malformed JSON string payload.
    observed_call = ObservedToolCall(
        call_id="call-001",
        event_id="evt-001",
        tool_name="getOrders",
        arguments='{"customerId": "CUST-27", status: INVALID_UNQUOTED}',
        raw_arguments='{"customerId": "CUST-27", status: INVALID_UNQUOTED}',
        is_arguments_malformed=True,
        is_unknown_tool=False,
        output=None,
        execution_status=ExecutionStatus.FAILED,
        error="JSONDecodeError: Expecting property name enclosed in double quotes",
    )

    # Observed call with status="REFUNDED"
    observed_wrong_call = ObservedToolCall(
        call_id="call-002",
        event_id="evt-002",
        tool_name="getOrders",
        arguments={"customerId": "CUST-27", "status": "REFUNDED"},
        execution_status=ExecutionStatus.COMPLETED,
    )

    trace = ExecutionTrace(
        project_id="J26-SE-341",
        case_id="TC-C1-001",
        run_id="run-101",
        execution_status=ExecutionStatus.COMPLETED,
        observed_calls=[observed_call, observed_wrong_call],
    )

    assert len(trace.observed_calls) == 2
    assert trace.observed_calls[0].is_arguments_malformed is True
    assert trace.observed_calls[1].arguments["status"] == "REFUNDED"


# 10. Test JSON Serialization Round Trips
def test_json_serialization_round_trips():
    project = create_sample_project()
    project_json = project.model_dump_json()
    project_reconstructed = ProjectInput.model_validate_json(project_json)
    assert project_reconstructed.project_id == project.project_id
    assert project_reconstructed.tools[0].tool_name == "getOrders"

    candidate = create_sample_candidate()
    candidate_json = candidate.model_dump_json()
    candidate_reconstructed = CandidateTestCase.model_validate_json(candidate_json)
    assert candidate_reconstructed.case_id == candidate.case_id
    assert (
        candidate_reconstructed.expected_calls[0]
        .argument_constraints["status"]
        .literal_value
        == "PAID"
    )

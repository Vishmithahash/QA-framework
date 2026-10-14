"""Tests for candidate reference model builder service."""

from app.components.c2_state_aware_workflow.contracts.workflow_input import (
    ToolSpecification,
    WorkflowInput,
    WorkflowRule,
)
from app.components.c2_state_aware_workflow.examples.refund_workflow import (
    get_draft_refund_workflow_input,
)
from app.components.c2_state_aware_workflow.services.model_builder import (
    ModelBuilderService,
)


class TestCandidateModelBuilder:
    """Verifies deterministic candidate model construction from normalized workflow inputs."""

    def test_build_candidate_from_supported_refund_input(self):
        builder = ModelBuilderService()
        wf_input = get_draft_refund_workflow_input()

        result = builder.build_candidate_model(
            workflow_input=wf_input,
            model_id="ecommerce-refund-candidate",
            version="1.0.0",
        )

        assert result.success is True
        assert result.candidate_model is not None
        model = result.candidate_model

        assert model.model_id == "ecommerce-refund-candidate"
        assert model.version == "1.0.0"
        assert model.project_id == "nexacart-qa-synthetic"
        assert model.domain == "e-commerce"

        # Structural completeness
        assert model.initial_state == "S_START"
        assert "S_REFUNDED" in model.accepting_states
        assert "S_REFUND_REJECTED" in model.expected_rejection_states
        assert len(model.states) >= 6
        assert len(model.transitions) >= 5

        # Invariants, entity continuity, and state effects
        assert len(model.invariants) >= 1
        assert len(model.entity_bindings) >= 1
        assert len(model.expected_state_effects) >= 2
        assert len(model.protected_fields) >= 2

        # Provenance, rules, and assumptions tracking
        assert result.builder_provenance == "deterministic_model_builder_v2"
        assert len(result.source_rules) >= 4
        assert any("RULE-CUSTOMER-OWNERSHIP" in r for r in result.source_rules)
        assert any("RULE-LATEST-ORDERING" in r for r in result.source_rules)
        assert len(result.assumptions) >= 2

    def test_builder_rejects_empty_rules_without_fabrication(self):
        builder = ModelBuilderService()
        insufficient_input = WorkflowInput(
            schema_version="1.0.0",
            project_id="test-proj",
            domain="e-commerce",
            task_description="Refund latest order",
            workflow_rules=[],  # Empty rules!
            tool_specifications=[
                ToolSpecification(
                    tool_name="refund_tool",
                    description="Issues refunds",
                    is_state_modifying=True,
                )
            ],
            observable_state_mappings=[],
            fixture_references=[],
        )

        result = builder.build_candidate_model(insufficient_input)
        assert result.success is False
        assert result.candidate_model is None
        assert any("No workflow_rules provided" in d for d in result.diagnostics)
        assert any("cannot be fabricated" in d for d in result.diagnostics)

    def test_builder_rejects_missing_tools(self):
        builder = ModelBuilderService()
        insufficient_input = WorkflowInput(
            schema_version="1.0.0",
            project_id="test-proj",
            domain="e-commerce",
            task_description="Refund latest order",
            workflow_rules=[
                WorkflowRule(
                    rule_id="R1",
                    name="Test Rule",
                    description="Rule 1",
                    rule_type="precondition",
                )
            ],
            tool_specifications=[],  # Empty tools!
            observable_state_mappings=[],
            fixture_references=[],
        )

        result = builder.build_candidate_model(insufficient_input)
        assert result.success is False
        assert result.candidate_model is None
        assert any("No tool_specifications provided" in d for d in result.diagnostics)

    def test_model_assisted_provider_integration(self):
        class MockLLMProvider:
            def __init__(self, succeed: bool = True):
                self.succeed = succeed

            def generate_candidate_model(self, workflow_input, temperature=0.0):
                if not self.succeed:
                    raise RuntimeError("Provider connection timeout")
                return {
                    "model_id": "llm-assisted-model",
                    "version": "1.0.0",
                    "schema_version": "1.0.0",
                    "project_id": workflow_input.project_id,
                    "domain": workflow_input.domain,
                    "name": "LLM Generated Model",
                    "description": "Synthesized by mock LLM",
                    "states": [
                        {"state_id": "S_START", "name": "Start", "is_initial": True},
                        {"state_id": "S_DONE", "name": "Done", "is_accepting": True},
                    ],
                    "initial_state": "S_START",
                    "accepting_states": ["S_DONE"],
                    "transitions": [
                        {
                            "transition_id": "T1",
                            "source_state": "S_START",
                            "target_state": "S_DONE",
                            "trigger_event": "EV_FINISH",
                        }
                    ],
                }

        # Successful provider call
        provider = MockLLMProvider(succeed=True)
        builder = ModelBuilderService(provider=provider)
        wf_input = get_draft_refund_workflow_input()
        result = builder.build_candidate_model(wf_input)
        assert result.success is True
        assert result.builder_provenance == "model_assisted_provider"
        assert result.candidate_model.model_id == "llm-assisted-model"

        # Fallback to deterministic builder on provider exception
        failing_provider = MockLLMProvider(succeed=False)
        fallback_builder = ModelBuilderService(provider=failing_provider)
        fallback_result = fallback_builder.build_candidate_model(wf_input)
        assert fallback_result.success is True
        assert fallback_result.builder_provenance == "deterministic_model_builder_v2"
        assert any(
            "fallback to deterministic" in d for d in fallback_result.diagnostics
        )

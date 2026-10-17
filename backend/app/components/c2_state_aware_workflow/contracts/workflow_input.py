"""Typed contract for workflow input specifications in Component 2.

Captures business requirements, allowed workflow rules, tool/API definitions,
observable state bindings, and synthetic fixture references.
"""

from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from app.components.c2_state_aware_workflow.contracts.predicates import (
    StructuredPredicate,
)


class WorkflowRule(BaseModel):
    """A business requirement or domain policy rule."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(
        ..., description="Unique rule identifier, e.g. 'RULE-REFUND-001'"
    )
    name: str = Field(..., description="Short name of the business rule")
    description: str = Field(..., description="Detailed description of the rule")
    rule_type: str = Field(
        ...,
        description="Category: 'precondition', 'ordering', 'invariant', 'rejection', 'lifecycle'",
    )
    predicate: StructuredPredicate | None = Field(
        default=None,
        description="Structured predicate formalizing this rule where applicable",
    )


class ToolSpecification(BaseModel):
    """Specification of an observable tool/API available to the agent."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(
        ..., description="Name of the tool/function, e.g. 'refund_order'"
    )
    description: str = Field(
        ..., description="Summary of tool purpose and side effects"
    )
    parameters_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON schema describing tool parameter signatures",
    )
    is_state_modifying: bool = Field(
        ...,
        description="True if tool mutates system state; False if read-only",
    )
    observable_events: list[str] = Field(
        default_factory=list,
        description="Names of events emitted or mapped to this tool call",
    )


class ObservableStateMapping(BaseModel):
    """Mapping between business entities, relational tables, and observable fields."""

    model_config = ConfigDict(extra="forbid")

    entity_name: str = Field(
        ..., description="Logical entity name, e.g. 'order', 'refund'"
    )
    source_table: str = Field(
        ..., description="Underlying database table or collection name"
    )
    key_field: str = Field(..., description="Primary identifier column name, e.g. 'id'")
    observable_fields: list[str] = Field(
        ...,
        description="Subset of columns observed for state transitions and side effects",
    )
    description: str | None = Field(
        default=None,
        description="Documentation of state observability semantics",
    )


class SyntheticFixtureReference(BaseModel):
    """Reference to a repeatable synthetic test fixture environment."""

    model_config = ConfigDict(extra="forbid")

    fixture_id: str = Field(..., description="Identifier of the synthetic fixture")
    domain: str = Field(..., description="Domain of the fixture, e.g. 'e-commerce'")
    description: str = Field(
        ..., description="Description of the initial environment state"
    )
    seed: int | None = Field(
        default=None,
        description="Deterministic PRNG seed used for fixture generation",
    )
    initial_entities: dict[str, Any] = Field(
        default_factory=dict,
        description="Seed records present in the fixture (e.g. customer 42, order 501)",
    )
    reset_hook: str | None = Field(
        default=None,
        description="Identifier or route of the fixture reset handler",
    )


class WorkflowInput(BaseModel):
    """Complete workflow input payload ingested by Component 2."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(
        default="1.0.0",
        description="Version of the workflow input contract schema",
    )
    project_id: str = Field(..., description="Project identifier, e.g. 'nexacart-qa'")
    domain: str = Field(
        ..., description="Business domain, e.g. 'e-commerce', 'flight-booking'"
    )
    task_description: str = Field(
        ...,
        description="Natural language description of the target workflow task",
    )
    workflow_rules: list[WorkflowRule] = Field(
        ...,
        description="Declared business rules governing the workflow",
    )
    tool_specifications: list[ToolSpecification] = Field(
        ...,
        description="Tools and APIs observable during workflow execution",
    )
    observable_state_mappings: list[ObservableStateMapping] = Field(
        ...,
        description="Database and state observability mappings",
    )
    fixture_references: list[SyntheticFixtureReference] = Field(
        ...,
        description="Synthetic test fixtures available for this workflow",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional additional metadata",
    )

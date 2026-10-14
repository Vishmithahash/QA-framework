# Component 1 (C1): Explainable Tool-Call Correctness Testing — Phase 1 Foundation

**Project Title**: Agentic AI-Based Software QA Framework for Testing Tool-Using LLM Applications  
**Project ID**: J26-SE-341  
**Component Identifier**: IT23236646 — Explainable Tool-Call Correctness Testing  
**Phase**: Phase 1 (Foundation, Contracts, and Pure Validation Services)  
**Architecture**: Modular Monolith internal package (`backend/app/components/c1_tool_call_correctness`)  

---

## 1. Phase 1 Scope & Architecture

Phase 1 establishes the verified domain contracts, pure validation services, status/evidence semantics, and integration architecture for Component 1 without claiming implementation of generative, execution, evaluation, diagnostic, or repair capabilities.

### Files Created & Organized
```text
backend/app/components/c1_tool_call_correctness/
├── __init__.py                                 # Component metadata, capability map, and exports
├── contracts/
│   ├── __init__.py                             # Re-exports all contracts
│   ├── base.py                                 # Enums, statuses, and ExplicitNull sentinel
│   ├── project_input.py                        # ProjectInput, RequirementDefinition, ToolCodeMappingReference
│   ├── tool_definition.py                      # ToolDefinition with JSON Schema parameters
│   ├── candidate_case.py                       # CandidateTestCase, ValueConstraint, ExpectedCallConstraint
│   ├── evidence.py                             # ObservedToolCall, ExecutionTrace, RuntimeEvidence
│   └── evaluation.py                           # EvaluationResult, CheckOutcome, DiagnosisResult
├── validators/
│   ├── __init__.py                             # Re-exports validators
│   ├── issue_codes.py                          # Stable issue codes (C1-PROJ-*, C1-TOOL-*, etc.)
│   ├── schema_validator.py                     # Draft-07/2020-12 validator without network resolution
│   ├── project_validator.py                    # ProjectInput validator (duplicates, refs, schemas)
│   └── candidate_validator.py                  # CandidateTestCase validator (assertions vs. schemas)
├── services/
│   ├── __init__.py                             # Re-exports services
│   └── validation_service.py                   # C1ValidationService orchestrating validation
└── docs/
    ├── SEMANTICS.md                            # Verdict and evidence evaluation specification
    └── PHASE_1_FOUNDATION.md                   # This implementation document
```

---

## 2. Contracts and Validation Rules

### A. Project Input (`ProjectInput`)
- Captures `project_id`, `domain` (e.g. NexaCart / e-commerce, examination-management), versioned `requirements`, `tools`, `agent_connection_ref`, and `fixture_config_ref`.
- **Secret Isolation**: Sensitive credentials are never embedded; secure references (`vault://...`, `fixture://...`) delegate secret handling to framework infrastructure.
- **Source-Code Access**: `source_code_ref` is optional for correctness testing (FR-01/FR-05) and required only for code-level diagnosis (FR-08).

### B. Tool Definitions (`ToolDefinition`)
- Defines `tool_id`, `tool_name`, `version`, `parameters_schema` (JSON Schema object), `output_schema`, and `requirement_refs`.
- Validated with `Draft202012Validator.check_schema` to guarantee valid structure.

### C. Candidate Test Cases & Structured Constraints (`CandidateTestCase`, `ValueConstraint`)
- Strictly forbids arbitrary Python expressions, shell commands, or raw SQL queries as assertions.
- Supported constraint types: `LITERAL`, `FIXTURE_FACT`, `SESSION_FACT`, `TOOL_OUTPUT_REF`.
- Validates declared expected literals against the tool's parameter JSON Schema before execution.
- Contradictory constraints or unsupported expression forms immediately flag `ValidationIssue` entries.

### D. Readiness vs. Agent Scoring
- An invalid candidate case is marked **`CaseReadiness.NOT_READY`** and excluded from test execution scoring.
- Invalid expectations **never** penalize the agent as a test `FAIL`.

---

## 3. Runtime Evidence & Status Semantics

### Representability of Erroneous Invocations
- `ObservedToolCall` records unparseable payloads (`is_arguments_malformed=True`, `raw_arguments="..."`), unrecognized tool names (`is_unknown_tool=True`), and runtime exceptions without rejecting the trace.
- Traces are never rejected at ingestion because they contain the exact tool-call errors C1 must evaluate.

### Missing Evidence vs. Explicit Null
- `output=None, output_is_explicit_null=False`: Output evidence was missing or omitted (triggers `INCONCLUSIVE` if mandatory).
- `output=None, output_is_explicit_null=True`: The tool invocation explicitly returned a JSON `null` / Python `None`.

### Core Verdict & Attribution Principles
1. **PASS**: Requires every mandatory check to succeed with verified runtime evidence in an uninterrupted run.
2. **FAIL**: Any mandatory check violation, unregistered tool call, missing argument, or type/value mismatch.
3. **INCONCLUSIVE**: Missing mandatory evidence or interrupted execution (`INTERRUPTED`).
4. **Value Provenance**: Matching a previous tool output does not prove origin without causal trace tags.
5. **Wrong Argument != Code Defect**: Evaluated as `AGENT_BEHAVIOUR` unless explicit evidence links it to code bugs.
6. **Isolation**: Original failure records remain permanently preserved and distinct from subsequent candidate patch verifications.

---

## 4. Requirement Coverage Matrix

| Requirement | Description | Status in Phase 1 | Implementation Notes |
|---|---|---|---|
| **FR-01** | Project requirements, tools, fixture references intake | **IMPLEMENTED** | `ProjectInput`, `ToolDefinition`, `RequirementDefinition` |
| **FR-02** | Automatic candidate tasks & expected-call generation | *PLANNED (Phase 2)* | Candidate schema defined; generation service deferred |
| **FR-03** | Pre-execution validation & frozen expectations | **IMPLEMENTED** | `C1ValidationService`, `CandidateTestCase`, `ValidationIssue` |
| **FR-04** | Fresh sessions, traces, call/argument/output capture | **IMPLEMENTED (Contract)** | `ObservedToolCall`, `ExecutionTrace`, `RuntimeEvidence` |
| **FR-05** | Tool correctness, argument types, values, task constraints | **IMPLEMENTED (Contract)** | `CheckOutcome`, `CheckType`, `ValueConstraint` |
| **FR-06** | Return PASS, FAIL, or INCONCLUSIVE | **IMPLEMENTED (Contract)** | `EvaluationVerdict`, `SEMANTICS.md` rules |
| **FR-07** | Explain expected vs. observed behavior with evidence | **IMPLEMENTED (Contract)** | `ReasonCode`, `CheckOutcome.message`, `SEMANTICS.md` |
| **FR-08** | Distinguish code defects, agent behaviour, spec problems | **IMPLEMENTED (Contract)** | `DiagnosisResult`, `DiagnosisClassification`, `SourceRelationStatus` |
| **FR-09** | Bounded candidate patch generation for code defects | *PLANNED (Phase 5)* | Deferred to repair phase |
| **FR-10** | Sandbox verification of patches (regression + acceptance) | *PLANNED (Phase 5)* | Deferred to repair phase |
| **FR-11** | Present verified candidates for developer review | *PLANNED (Phase 6)* | Deferred to persistence and API phase |
| **FR-12** | Audit retention, filtering, and authorized report export | *PLANNED (Phase 6)* | Multi-phase audit retention model designed |

### Non-Functional Requirements (NFR)
| NFR | Scope | Status | Notes |
|---|---|---|---|
| **NFR-01** | Modular Monolith Integration | **VERIFIED** | Internal Python package under `app/components/` |
| **NFR-02** | Deterministic Validation | **VERIFIED** | Pure in-memory services without external network calls |
| **NFR-03** | Schema Safety | **VERIFIED** | JSON Schema Draft 7/2020-12 validation with network resolution disabled |
| **NFR-04** | Secret Security | **VERIFIED** | Credential isolation via URI references |
| **NFR-05** | Scale: 50+ cases per run | *PLANNED (Phase 3)* | Lightweight Pydantic models designed for memory efficiency |
| **NFR-06** | Concurrency: 2 simultaneous project runs | *PLANNED (Phase 3)* | Stateless validation services |
| **NFR-07** | Traceability & Versioning | **VERIFIED** | Requirement and tool version pinning on all candidate cases |
| **NFR-08** | Code Quality & Tests | **VERIFIED** | 100% test pass rate with pytest and ruff formatting |

---

## 5. Roadmap for Subsequent Phases

- **Phase 2**: Generation, validation, and frozen expectations (LLM synthesis, data preparation plans, task templates).
- **Phase 3**: Execution orchestration, live traces, and tool-call correctness evaluation (PASS / FAIL / INCONCLUSIVE evaluator).
- **Phase 4**: Explainable analysis, causal data-flow tracking, and code defect diagnosis (AST and stack correlation).
- **Phase 5**: Candidate code repair, bounded patch generation, and sandboxed regression verification.
- **Phase 6**: Persistence layer (Neon PostgreSQL models, Alembic migrations), REST APIs, developer review workflow, and export.
- **Phase 7**: Baselines (NexaCart, examination domain), held-out dataset splits, ablation studies, and final reproducibility audit.

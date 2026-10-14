# Component 2: State-Aware Multi-Step Workflow Testing

Component 2 (C2) of the **Agentic AI-Based Software QA Framework for Testing Tool-Using LLM Applications**.

This component provides automated, state-aware testing of multi-step LLM agent workflows against an Extended Finite State Machine (EFSM) correctness oracle, observing ordered events and intermediate application state to localise the earliest workflow-state divergence.

---

## 1. Component Purpose & Research Problem

Tool-using Large Language Model (LLM) agents can call individually valid tools and still fail multi-step business tasks by:
- Skipping required eligibility checks or preconditions.
- Executing workflow actions in the wrong order.
- Violating lifecycle guards or domain invariants.
- Switching entity identity during the workflow (entity discontinuity).
- Leaving required database side effects unfulfilled or mutating protected state.
- Terminating prematurely before reaching the target business outcome.

Existing evaluation approaches check final database states (missing intermediate deviations) or trace tool names (failing to verify underlying database effects). Component 2 bridges this gap by combining:
1. A validated, versioned **EFSM reference oracle**.
2. **Coverage-guided path and mutation generation**.
3. **Trace-to-state alignment** linking runtime events with before-and-after database observations.
4. **First-divergence localisation** identifying the exact step where execution departed from valid model paths.

---

## 2. Individual Responsibility Boundary

In accordance with the framework architecture:

| Area | Component 2 Responsibility | Other Components / Shared Platform |
|---|---|---|
| **EFSM Behavioral Oracle** | Owns schema, definition, invariants, guards, and version store | Shared intake reviews workflow inputs |
| **Workflow Test Generation** | Owns coverage-guided normal, alternative, and mutated path generation | C3 consumes test cases for fault trials |
| **Runtime Evidence & State** | Owns state diff evaluation, entity continuity, and observation normalisation | Shared evidence store handles transport and storage |
| **Conformance Checking** | Owns trace-to-state alignment and first-divergence localisation | Shared runner executes the tested agent |
| **Coverage & Reporting** | Computes transition, guard, path, and state-effect coverage | Shared reporting engine aggregates with C1, C3, C4 |
| **Individual Tool Call Validation** | Excluded | **Component 1 (C1)** |
| **Operational Faults & Recovery** | Excluded | **Component 3 (C3)** |
| **Policy Safety & Prompt Injection** | Excluded | **Component 4 (C4)** |

---

## 3. Phase 1 Implemented Foundation

### 3.1 Typed Pydantic Contracts (`contracts/`)

- **Workflow Input (`WorkflowInput`)**: Captures project/domain identifiers, task descriptions, declarative workflow rules, tool/API specifications, observable state mappings, and synthetic fixture references.
- **FSM/EFSM Behavioral Model (`WorkflowModelDefinition`)**: Captures states, initial state, accepting states, expected rejection states, variables with declared input domains, transitions with unique IDs, observable event mappings, milestones, entity continuity rules, expected state effects, protected fields, and final outcome conditions.
  - *Declarative AST Predicates*: Structured predicates (`StructuredPredicate`) evaluate leaf operators (`eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `is_null`, `is_not_null`, `contains`, `matches_entity`) and composites (`and`, `or`, `not`) without executing user-supplied code via `eval`, `exec`, SQL, or shell commands.
- **Generated Test Contract (`GeneratedWorkflowTest`)**: Captures test ID/version, model version, categories (`NORMAL`, `ALTERNATIVE`, `NEGATIVE`, `MUTATED`), task prompt, synthetic fixture reference, PRNG seed, expected outcome, private reference path (hidden from tested agent), mutation provenance (`SKIPPED_STEP`, `REORDERED_STEP`, `REPEATED_STEP`, `ILLEGAL_TRANSITION`, `WRONG_ENTITY`, `MISSING_EFFECT`), and readiness tracking.
- **Runtime Evidence Contract (`RuntimeEvidenceEvent`, `WorkflowExecutionEvidence`)**: Captures ordered events, sequence index, tool call ID, timestamps, tool results/errors, entity IDs, before/after observations, state diffs, and evidence completeness.
  - *Tri-State Evidence Distinction*: Uses `ObservedValue` to explicitly distinguish between `PRESENT` (concrete value), `EXPLICIT_NULL` (inspected field is verified null in system state), and `MISSING` (observation absent, unrecorded, or query failed).
- **Evaluation Result Contract (`WorkflowEvaluationResult`)**: Captures pinned model/test versions, expected and observed state sequences, violations, first-divergence localisation, evidence citations, coverage metrics, and evaluator timing.
  - *Exact Six Mandated Verdicts*:
    1. `PASS`
    2. `EXPECTED REJECTION PASS`
    3. `FAIL`
    4. `INCONCLUSIVE`
    5. `MODEL NOT READY`
    6. `TEST NOT READY`

### 3.2 Model Storage & Lifecycle (`models/`, `services/`)

- **SQLAlchemy ORM Model (`C2WorkflowModel`)**: Persisted in table `c2_workflow_models` with columns for `model_id`, `version`, `schema_version`, `project_id`, `domain`, `name`, `description`, structured JSON `definition`, `content_hash`, `lifecycle_status`, timestamps, and review/approval audit metadata.
- **Unique Constraint**: `(project_id, model_id, version)` enforces strict versioning per project.
- **Deterministic Content Hashing**: Computes canonical SHA-256 hashes using uniform key ordering and compact JSON delimiters (`compute_canonical_content_hash`).
- **Lifecycle Integrity**: All models created in Phase 1 are strictly assigned `DRAFT`. Approved-version immutability (`ApprovedModelImmutableError`) ensures approved models cannot be overwritten or mutated.
- **Alembic Migration**: `001_c2_create_workflow_models.py` defines full forward and rollback DDL.

### 3.3 Draft API Endpoints (`router.py`)

Registered under `/api/v1/c2`:
- `POST /api/v1/c2/models`: Validates and creates a draft workflow reference model (201 Created). Returns 409 Conflict if `(project_id, model_id, version)` already exists.
- `GET /api/v1/c2/models?project_id=...`: Lists workflow model summaries for a given project, with optional `domain` and `lifecycle_status` query filters.
- `GET /api/v1/c2/models/{model_id}/versions/{version}`: Retrieves full model details including definition JSON. Returns 404 Not Found if missing.

### 3.4 Shared Integration Interfaces (`interfaces/`)

Defines narrow Python `typing.Protocol` interfaces:
1. `WorkflowInputNormalizationInterface`: Interface to Shared Project Intake.
2. `FixtureResetInterface`: Interface to Shared Fixture Manager.
3. `AgentExecutionInterface`: Interface to Shared Agent Runner.
4. `StateObservationInterface`: Interface to Runtime State Observer / AUT Adapter.
5. `EvidenceIngestionInterface`: Interface to Shared Evidence Store.
6. `UnifiedReportExportInterface`: Interface to Shared Report Aggregator.

### 3.5 Synthetic Draft Refund Example (`examples/`)

Implements the draft EFSM for **"Refund my latest paid order"**:
- **Conceptual Path**: `Start -> Paid Orders Retrieved -> Latest Eligible Order Identified -> Refund Requested -> Refunded`
- **Synthetic Entities**: Customer 42, older paid order 501 ($45.00), later paid order 503 ($89.00), unpaid order 502.
- **Latest Ordering Rule**: Explicit rule selecting order 503 over 501 because `created_at(503) > created_at(501)`.
- **Entity Continuity**: Order 503 identity is maintained across identification, refund request, and confirmation steps (`ECR_ORDER_503_CONTINUITY`).
- **Invariant**: No refund for unpaid orders (`INV_NO_UNPAID_REFUND`).
- **State Effects**: Refund record created (`status = COMPLETED`), order payment status updated (`payment_status = REFUNDED`).
- **Protected Fields**: Customer 42 profile and older order 501 remain strictly immutable.
- **Expected Rejection**: Invalid/unpaid request transitions to `Refund Rejected` with protected state unchanged.

---

## 4. API Usage Examples

### 4.1 Create Draft Model

**Request:**
```http
POST /api/v1/c2/models HTTP/1.1
Content-Type: application/json

{
  "project_id": "nexacart-qa-synthetic",
  "domain": "e-commerce",
  "name": "Refund Latest Paid Order Workflow",
  "description": "Synthetic behavioral EFSM oracle for 'Refund my latest paid order'",
  "definition": {
    "model_id": "ecommerce-refund-latest-paid",
    "version": "1.0.0",
    "schema_version": "1.0.0",
    "project_id": "nexacart-qa-synthetic",
    "domain": "e-commerce",
    "name": "Refund Latest Paid Order Workflow",
    "states": [
      {"state_id": "S_START", "name": "Start", "is_initial": true},
      {"state_id": "S_PAID_ORDERS_RETRIEVED", "name": "Paid Orders Retrieved"},
      {"state_id": "S_LATEST_ORDER_IDENTIFIED", "name": "Latest Eligible Order Identified"},
      {"state_id": "S_REFUND_REQUESTED", "name": "Refund Requested"},
      {"state_id": "S_REFUNDED", "name": "Refunded", "is_accepting": true},
      {"state_id": "S_REFUND_REJECTED", "name": "Refund Rejected", "is_expected_rejection": true}
    ],
    "initial_state": "S_START",
    "accepting_states": ["S_REFUNDED"],
    "expected_rejection_states": ["S_REFUND_REJECTED"],
    "variables": [
      {"name": "customer_id", "var_type": "int", "declared_input_domain": [42]},
      {"name": "selected_order_id", "var_type": "int", "declared_input_domain": [501, 503]}
    ],
    "transitions": [
      {
        "transition_id": "T1_RETRIEVE_PAID_ORDERS",
        "source_state": "S_START",
        "target_state": "S_PAID_ORDERS_RETRIEVED",
        "trigger_event": "EV_ORDERS_RETRIEVED",
        "guards": [
          {"field": "customer_id", "operator": "eq", "value": 42}
        ]
      }
    ]
  }
}
```

**Response (201 Created):**
```json
{
  "id": "e7b0c360-1b29-4d69-a1d2-94b8e8f81a89",
  "model_id": "ecommerce-refund-latest-paid",
  "version": "1.0.0",
  "schema_version": "1.0.0",
  "project_id": "nexacart-qa-synthetic",
  "domain": "e-commerce",
  "name": "Refund Latest Paid Order Workflow",
  "description": "Synthetic behavioral EFSM oracle for 'Refund my latest paid order'",
  "content_hash": "a1b2c3d4e5f6...",
  "lifecycle_status": "DRAFT",
  "created_at": "2026-10-13T10:00:00Z",
  "updated_at": "2026-10-13T10:00:00Z",
  "definition": { ... },
  "review_notes": null,
  "reviewed_by": null,
  "reviewed_at": null,
  "approved_by": null,
  "approved_at": null
}
```

### 4.2 List Models for Project

**Request:**
```http
GET /api/v1/c2/models?project_id=nexacart-qa-synthetic HTTP/1.1
```

**Response (200 OK):**
```json
[
  {
    "id": "e7b0c360-1b29-4d69-a1d2-94b8e8f81a89",
    "model_id": "ecommerce-refund-latest-paid",
    "version": "1.0.0",
    "schema_version": "1.0.0",
    "project_id": "nexacart-qa-synthetic",
    "domain": "e-commerce",
    "name": "Refund Latest Paid Order Workflow",
    "description": "Synthetic behavioral EFSM oracle for 'Refund my latest paid order'",
    "content_hash": "a1b2c3d4e5f6...",
    "lifecycle_status": "DRAFT",
    "created_at": "2026-10-13T10:00:00Z",
    "updated_at": "2026-10-13T10:00:00Z"
  }
]
```

### 4.3 Get Model Version

**Request:**
```http
GET /api/v1/c2/models/ecommerce-refund-latest-paid/versions/1.0.0 HTTP/1.1
```

**Response (200 OK):**
Full detail payload including the complete structured EFSM definition.

---

## 5. Remaining Implementation Phases

| Phase | Scope & Key Deliverables |
|---|---|
| **Phase 2: Test & Mutation Generation** | Bounded path exploration; mutation engine (`SKIPPED_STEP`, `REORDERED_STEP`, `REPEATED_STEP`, `ILLEGAL_TRANSITION`, `WRONG_ENTITY`, `MISSING_EFFECT`); feasibility filter returning `TEST NOT READY`. |
| **Phase 3: Observation & Execution** | Runtime state observer; AUT PostgreSQL adapter; before/after snapshot collector; event normalisation and fixture reset orchestration. |
| **Phase 4: Conformance & Localisation** | Trace-to-EFSM alignment engine; multi-path backtracking; guard & invariant evaluation; first-divergence localisation algorithm. |
| **Phase 5: Reporting & Empirical Evaluation** | Coverage calculation (transition, guard, path, effect); unified report export; benchmark experiments against B1 (Final-state), B2 (Trace-only), and B3 (Milestone-based) baselines across e-commerce, flight-booking, and LMS workflows. |

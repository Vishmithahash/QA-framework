# Backend Foundation - Agentic AI QA Framework

Backend foundation for the **Agentic AI-Based Software QA Framework for Testing Tool-Using LLM Applications**.

Provides a FastAPI backend with environment configuration, Neon PostgreSQL connectivity via SQLAlchemy 2.0 and psycopg 3, Alembic migrations, health check endpoints, and automated tests.

---

## Architecture: Modular Monolith

- The QA framework is structured as a **modular monolith** within a single FastAPI application and codebase.
- Application configuration, Neon PostgreSQL database connections, SQLAlchemy base/session models, and Alembic migrations are shared across the system.
- The four research components are organized as internal Python packages under `app/components/` and communicate via internal Python interfaces rather than separate services.
- The reserved component packages currently contain only empty package markers and no runtime implementation.

### Reserved Research Components

The component packages under `app/components/` map to the research components as follows:

| Package Folder | Research Component |
|---|---|
| `c1_tool_call_correctness` | **C1: Explainable Tool-Call Correctness Testing** |
| `c2_state_aware_workflow` | **C2: State-Aware Multi-Step Workflow Testing** |
| `c3_robustness_recovery` | **C3: Robustness and Failure Recovery Testing** |
| `c4_policy_prompt_injection` | **C4: Policy-Aware Safety and Prompt-Injection Testing** |

### Shared Integration Agreements (Design Note)

The following integration agreements will be finalized prior to component implementation:

- **Entity & Event Identifiers**: Future test and evidence records will share consistent `project_id`, `case_id`, `run_id`, and `event_id` fields. C3 will additionally include trial identifiers linking matched clean and fault trials.
- **Run Metadata**: Each run will identify associated fixtures, agent/model configuration, component contracts, and evaluator versions.
- **Status & Verdict Separation**: Readiness, execution status, exposure status, and component verdicts must remain strictly decoupled.
- **Component Interoperability**: C2 owns workflow/state assertion definitions, while C3 consumes their `true`/`false`/`unknown` facts. Each component owns its generation and evaluation rules.
- **Shared Infrastructure**: Execution orchestration, fixture reset mechanisms, and evidence transport will be designed once at the application level.
- **Defect Correlation**: Related findings will reference shared events to prevent duplicate counting of the same root defect.
- **Database Separation**: The QA framework's Neon database is strictly dedicated to framework state/evidence and isolated from any application-under-test (AUT) databases.

---

## Getting Started

Run all commands from the `backend/` directory.

### 1. Verify Python Version (3.12+)

```powershell
python --version
```

### 2. Create and Activate Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Direct Dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure Environment

Copy `.env.example` to `.env`:

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**macOS / Linux:**
```bash
cp .env.example .env
```

### 5. Configure Neon Database URL

Edit `.env` and set your Neon connection string. Use a direct connection string or pooled connection string with `sslmode=require`:

```env
DATABASE_URL="postgresql://username:password@hostname/database?sslmode=require"
```

### 6. Verify Alembic Migrations

Check current migration revision:

```powershell
alembic current
```

> **Note on Migrations**: No revisions exist during initial foundation setup. Once application models are introduced in later stages, apply new migrations using:
> ```powershell
> alembic upgrade head
> ```

### 7. Start Development Server

```powershell
uvicorn app.main:app --reload
```

### 8. Interactive API Documentation

Visit [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) (or [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)).

### 9. Health & Database Check

- Root: `GET http://127.0.0.1:8000/` -> `{"message": "Agentic AI QA Framework API", "status": "running"}`
- Liveness: `GET http://127.0.0.1:8000/health` -> `{"status": "healthy"}`
- Database: `GET http://127.0.0.1:8000/health/db` -> `{"status": "healthy", "database": "connected"}`

### 10. Run Tests, Linting, and Formatting

```powershell
# Run unit tests
pytest

# Run Ruff linter
ruff check .

# Check code formatting
ruff format --check .
```

---

## Component 3 (C3): Robustness and Failure Recovery Testing (Phase 1)

Phase 1 provides a small, stateless foundation within the existing backend for static candidate case validation and operational fault catalogue inspection:

- **Input Contracts**: Versioned Pydantic v2 schemas (`CaseValidationRequest`, `AdapterCapabilityManifest`, `CandidateFaultCase`, `RecoveryContract`, `EnvironmentMetadata`).
- **Operational Fault Catalogue**: Five operational fault families with parameter constraints (`TIMEOUT_OR_DISCONNECTION`, `TRANSIENT_5XX_SERVER_ERROR`, `HTTP_429_RATE_LIMITING`, `TOOL_UNAVAILABILITY`, `MALFORMED_OR_TRUNCATED_RESPONSE`). Active injection is not implemented in this phase.
- **Static Validator**: Pure deterministic validation function verifying declaration alignment without database or network access.
- **Important Boundary**: Static validation (`STATIC_VALID`) establishes only metadata and capability declaration consistency. It **does not** establish runtime readiness, adapter capability verification, live exposure, or agent recovery verdicts (`execution_ready` is always `false`, `recovery_verdict` is always `null`).

### C3 Endpoints

1. `GET /api/v1/c3/fault-catalog`
   - Returns the five operational fault families, parameter constraints, and the explicit indication that fault injection is not implemented.
2. `POST /api/v1/c3/cases/validate`
   - Accepts a `CaseValidationRequest` and statically validates capability alignment, version consistency, effect phases, and recovery budgets.
   - Returns HTTP 200 with `validation_status: "STATIC_VALID"` or `"TEST_NOT_READY"`.
   - Returns HTTP 422 with sanitized field error details for malformed JSON or invalid schema structures without echoing raw input values.

### Example: Statically Consistent Validation Request & Response

**Request (`POST /api/v1/c3/cases/validate`):**
```json
{
  "case": {
    "schema_version": "1.0.0",
    "project_id": "proj-ecom-01",
    "case_id": "case-payment-timeout-01",
    "case_family": "CF-PAYMENT-TIMEOUT",
    "domain": "e-commerce",
    "task_id": "task-checkout-01",
    "task_version": "1.0.0",
    "tool_id": "charge_payment",
    "tool_version": "1.0.0",
    "fixture_id": "fix-cart-empty",
    "fixture_version": "1.0.0",
    "adapter_id": "adapter-gateway-01",
    "adapter_version": "1.0.0",
    "recovery_contract_id": "rec-standard-01",
    "recovery_contract_version": "1.0.0",
    "trigger": {
      "tool_id": "charge_payment",
      "call_occurrence": 1,
      "hook": "DURING_TRANSPORT"
    },
    "fault_family": "TIMEOUT_OR_DISCONNECTION",
    "effect_phase": "BEFORE_EFFECT",
    "payload": {
      "family": "TIMEOUT_OR_DISCONNECTION",
      "mode": "CONNECTION_TIMEOUT",
      "delay_ms": 5000
    },
    "release_rule": {
      "mode": "SINGLE_CALL",
      "max_fault_occurrences": 1
    },
    "required_assertion_ids": ["assert_order_not_duplicated"],
    "seed": 42
  },
  "adapter_manifest": {
    "schema_version": "1.0.0",
    "adapter_id": "adapter-gateway-01",
    "adapter_version": "1.0.0",
    "tools": [
      {
        "tool_id": "charge_payment",
        "tool_version": "1.0.0",
        "is_side_effecting": true
      }
    ],
    "capabilities": [
      {
        "fault_family": "TIMEOUT_OR_DISCONNECTION",
        "effect_phase": "BEFORE_EFFECT",
        "hook": "DURING_TRANSPORT",
        "observation_method": "obs_network_trace",
        "min_delay_ms": 100,
        "max_delay_ms": 10000,
        "supported_release_modes": ["SINGLE_CALL"]
      }
    ]
  },
  "recovery_contract": {
    "contract_id": "rec-standard-01",
    "version": "1.0.0",
    "permitted_terminal_outcomes": ["SUCCESS", "GRACEFUL_DEGRADATION"],
    "graceful_stopping_conditions": ["max_retries_reached"],
    "max_total_attempts": 3,
    "max_retries": 2,
    "timeout_budget_seconds": 30.0,
    "required_assertion_ids": ["assert_order_not_duplicated"],
    "allow_duplicate_side_effects": false,
    "truthful_completion_required": true,
    "forbid_unsafe_retries": true,
    "rule_ids": ["REC-01-NO-DUPLICATE"]
  },
  "environment_metadata": {
    "task": {
      "task_id": "task-checkout-01",
      "task_version": "1.0.0",
      "domain": "e-commerce"
    },
    "fixture": {
      "fixture_id": "fix-cart-empty",
      "fixture_version": "1.0.0",
      "supports_reset": true,
      "supports_observation": true,
      "has_commit_observation": true
    },
    "available_assertions": [
      {
        "assertion_id": "assert_order_not_duplicated",
        "assertion_type": "STATE_INVARIANT",
        "description": "Verifies no duplicate charge"
      }
    ],
    "observation_methods": [
      {
        "method_id": "obs_network_trace",
        "description": "Network delay monitor"
      }
    ]
  }
}
```

**Response (HTTP 200 OK):**
```json
{
  "validation_scope": "STATIC_ONLY",
  "validation_status": "STATIC_VALID",
  "execution_ready": false,
  "pending_checks": [
    "actual_fixture_reset",
    "trigger_reachability",
    "observation_access",
    "injection_effect_phase_fidelity_verification"
  ],
  "reasons": [],
  "recovery_verdict": null
}
```

### Example: Rejected Candidate Case (`TEST_NOT_READY`)

When a candidate case requests an undeclared capability combination (or violates phase constraints such as declaring `AFTER_COMMIT` without application-aware hook / commit observation), HTTP 200 is returned with structured reasons:

**Response (HTTP 200 OK):**
```json
{
  "validation_scope": "STATIC_ONLY",
  "validation_status": "TEST_NOT_READY",
  "execution_ready": false,
  "pending_checks": [],
  "reasons": [
    {
      "code": "CAPABILITY_COMBINATION_NOT_DECLARED",
      "message": "The exact combination of fault family, effect phase, hook, and release rule is not declared in the adapter capability manifest.",
      "field_path": "adapter_manifest.capabilities"
    }
  ],
  "recovery_verdict": null
}
```

### Next Increment (Phase 2 & Beyond)

Phase 2 builds the executable vertical slice: matched clean/fault trials, one-shot `BEFORE_EFFECT` timeout interception, fixture isolation/observation, and verified exposure receipts.

---

## Component 3 (C3): Robustness and Failure Recovery Testing (Phase 3)

Phase 3 hardens the paired-trial runtime, decouples fault exposure from clean qualification, adds strict per-tool occurrence counting and thread-safe atomic consumption, introduces scoped fixture partitioning and post-trial settling observation, verifies genuine transport socket timeouts, and truthful reporting of live prerequisites.

### 1. Internal Package Organization

The Component 3 codebase is organized into clear internal packages by responsibility:

```text
app/components/c3_robustness_recovery/
    __init__.py
    contracts/
        __init__.py
        schemas.py          # Pure Pydantic v2 data, trigger, capability, and validation schemas
        generation.py       # Generation requests, responses, policies, and frozen suite contracts
    services/
        __init__.py
        validation.py       # Pure deterministic static capability and candidate case validator
        generation.py       # Candidate generation, deduplication, and bounded round-robin selection
        suites.py           # Canonical JSON hashing, SHA-256 suite digests, integrity checks, and export
    runtime/
        __init__.py
        adapter.py          # ToolAdapter, FixtureManager, in-memory double, and live blocked skeletons
        evidence.py         # Runtime evidence contracts, linkage validation, and artifact export
        interceptor.py      # Thread-safe OneShotTimeoutInterceptor gateway
        runner.py           # Matched-pair runner and developer CLI
    api/
        __init__.py
        router.py           # FastAPI APIRouter exposing C3 HTTP endpoints
```

All C3 references across the repository import directly from these canonical paths. The CLI runner is executed via `python -m app.components.c3_robustness_recovery.runtime.runner`.

### 2. Actual Supported Runtime Capability
- **Targeted Fault Family**: `TIMEOUT_OR_DISCONNECTION` exclusively for runtime execution.
- **Effect Phase**: `BEFORE_EFFECT` exclusively.
- **Release Rule**: Single-call one-shot release (`SINGLE_CALL` or `COUNT_BASED` with `max_fault_occurrences=1`).
- **Hook**: `DURING_TRANSPORT` or `PRE_TOOL_INVOCATION`.
- **Target Tool**: `create_order` (side-effecting domain tool).
- **Runtime Validation**: Rejects unsupported execution configurations before execution rather than silently misbehaving.

### 3. Demonstration vs. Live Modes
- **Demonstration Mode (`TargetMode.FAKE_ADAPTER`, `CallerIdentity.SCRIPTED_CALLER`)**:
  - Uses `FakeNexaCartOrderToolAdapter` and `FakeNexaCartFixtureManager`.
  - Operates hermetically without external network or database dependencies.
  - Retries initiated by the scripted caller are labeled `RecoveryActor.SCRIPTED_CALLER` and never misattributed to agent decisions.
- **Live Target Mode (`TargetMode.LIVE_AUT`)**:
  - Connects to genuine application-under-test tools via `NexaCartHttpToolAdapter` and `NexaCartPrismaFixtureManager`.
  - **No Silent Fallback**: Live mode never falls back to fake adapters; missing configuration raises `IntegrationBlockedError`.
  - **CLI Nonzero Exit**: Invoking live mode via CLI when prerequisites are missing exits with documented code 2 and an explicit `[BLOCKED]` message.
  - **Status: BLOCKED**. Inspection confirms that no NexaCart source code, Prisma schema, or OpenAPI definition currently exists in the repository.
- **Live Agent Mode (`CallerIdentity.ACTUAL_TESTED_AGENT`)**:
  - Requires domain tool routing through the C3 interceptor while leaving LLM-provider calls untouched.
  - **Status: BLOCKED**. No agent invocation protocol or tested agent implementation currently exists in the repository.

### 4. Prerequisites for Unblocking Live Execution
To unblock live integration without mock or fake fallbacks, the following prerequisites must be provisioned:
1. **Target OpenAPI/Tool Contract**: Authoritative endpoint definitions for `create_order` (request/response schemas, idempotency keys, error models).
2. **Dedicated Test Database**: `NEXACART_DATABASE_URL` pointing to an isolated test database (e.g. `postgresql://user:pass@localhost:5433/nexacart_test`). Must **never** point to the QA framework Neon database (enforced by normalized database identity checks).
3. **HTTP Service**: `NEXACART_BASE_URL` pointing to the running AUT instance (e.g. `http://localhost:3000`).
4. **Agent Protocol**: Invocation protocol allowing domain tool interception without altering agent recovery logic.

Example placeholder environment variables in `.env` (opt-in only):
```env
# Dedicated AUT Target (Isolated test instance - DO NOT point at QA Neon DB)
NEXACART_BASE_URL="http://localhost:3000"
NEXACART_DATABASE_URL="postgresql://nexacart_tester:secret@localhost:5433/nexacart_test?sslmode=require"
```

### 5. Running the Hardened Developer CLI

Run commands from the `backend/` directory using the existing virtual environment:

```powershell
# Standard local paired-trial runner (demonstration mode, exit code 0)
.\.venv\Scripts\python.exe -m app.components.c3_robustness_recovery.runtime.runner --output-dir ./evidence_output

# Fast synthetic timeout mode (exit code 0)
.\.venv\Scripts\python.exe -m app.components.c3_robustness_recovery.runtime.runner --synthetic --output-dir ./evidence_output

# Live AUT mode (will report BLOCKED and exit with code 2)
.\.venv\Scripts\python.exe -m app.components.c3_robustness_recovery.runtime.runner --live
```

---

## Component 3 (C3): Robustness and Failure Recovery Testing (Phase 4)

Phase 4 adds automated candidate fault case generation, static deduplication, bounded selection, and content-addressed frozen suite creation.

### 1. Generation Scope & Pure Functions
- **Pure Stateless Execution**: `generate_fault_suite` performs candidate derivation, static validation, deduplication, and selection without database queries, network requests, LLM calls, or runner executions.
- **Exact Capability Combinations**: Generates only from explicit capability records declared in the adapter manifest (`AdapterCapability`). Never assumes support through combinatorial cross-products of independent lists.
- **5 Fault Families Covered**: Derives valid boundary and representative payload parameters across all catalogue families (`TIMEOUT_OR_DISCONNECTION`, `TRANSIENT_5XX_SERVER_ERROR`, `HTTP_429_RATE_LIMITING`, `TOOL_UNAVAILABILITY`, `MALFORMED_OR_TRUNCATED_RESPONSE`).
- **Static Validation Pass**: Every generated candidate passes through `validate_candidate_case`. Only statically valid cases can be selected.
- **Examination Budget**: Controlled by `policy.max_candidates_examined` (1–1,000). Stops derivation when the budget is reached and explicitly reports `is_truncated: true` and `candidate_population_denominator: null`.

### 2. Semantic Deduplication and Selection
- **Semantic Fingerprinting**: Hashes only meaningful case semantics (task, tool, adapter, fixture, recovery contract, trigger occurrence, hook, payload parameters, release rule, assertions, caller timeout). Generated identifiers (`case_id`), display labels, and timestamps are excluded.
- **Stable Identifiers**: Case identifiers (`case-{fp[:8]}`) and case families (`fam-{tool_id}-{family}-{phase}`) are deterministically derived from the semantic fingerprint.
- **Input Ordering Independence**: Inputs are canonically sorted prior to enumeration; array reordering in requests produces identical suites and content digests.
- **Seeded Round-Robin Selection**: Unique candidates are grouped by `(tool_id, fault_family)`. Selection proceeds round-robin across groups up to `policy.max_cases` (1–50). Providing a `seed` yields deterministic pseudo-random shuffling within groups.

### 3. Frozen Versioned Suites & Content Digests
- **Content-Addressed Digest**: Uses `hashlib.sha256` over the canonical JSON representation (sorted keys, compact separators, no non-finite numbers) of frozen suite contents.
- **Digest Coverage**: Covers generator version, policy, non-secret input snapshots, selected cases, recovery contracts, fingerprints, case families, counters, and limitations. Excludes `content_digest`, `suite_id`, and nondeterministic `created_at_utc`.
- **Integrity Verification**: `verify_suite_integrity(suite)` recomputes the canonical digest to detect corruption or tampering before future execution.
- **Defensive Snapshotting**: Deep-copies all inputs so mutating caller objects after generation cannot affect the frozen suite.
- **Local Developer Export**: `export_frozen_suite(suite, path, overwrite=False)` writes versioned JSON to disk, validating integrity first and preventing accidental overwriting.

### 4. Generation Endpoint (`POST /api/v1/c3/cases/generate`)

Generates a bounded suite from declared system metadata and requirements.

**Request (`POST /api/v1/c3/cases/generate`):**
```json
{
  "schema_version": "1.0.0",
  "project_id": "proj-nexacart-qa",
  "tasks": [
    {
      "task_id": "task-checkout-flow",
      "task_version": "1.0.0",
      "domain": "e-commerce"
    }
  ],
  "adapter_manifests": [
    {
      "schema_version": "1.0.0",
      "adapter_id": "adapter-payment-order",
      "adapter_version": "1.0.0",
      "tools": [
        {
          "tool_id": "create_order",
          "tool_version": "1.0.0",
          "is_side_effecting": true
        }
      ],
      "capabilities": [
        {
          "fault_family": "TIMEOUT_OR_DISCONNECTION",
          "effect_phase": "BEFORE_EFFECT",
          "hook": "DURING_TRANSPORT",
          "observation_method": "obs_network_trace",
          "tool_id": "create_order",
          "max_call_occurrence": 2,
          "allowed_modes": ["CONNECTION_TIMEOUT", "READ_TIMEOUT"],
          "min_delay_ms": 100,
          "max_delay_ms": 5000,
          "supported_release_modes": ["SINGLE_CALL"]
        }
      ]
    }
  ],
  "fixtures": [
    {
      "fixture_id": "fix-order-db",
      "fixture_version": "1.0.0",
      "supports_reset": true,
      "supports_observation": true,
      "has_commit_observation": true,
      "has_partial_effect_observation": true
    }
  ],
  "recovery_contracts": [
    {
      "contract_id": "rec-standard-01",
      "version": "1.0.0",
      "permitted_terminal_outcomes": ["SUCCESS", "SAFE_ABORT"],
      "graceful_stopping_conditions": ["max_retries_exceeded"],
      "max_total_attempts": 3,
      "max_retries": 2,
      "timeout_budget_seconds": 30.0,
      "required_assertion_ids": ["assert_order_recorded"],
      "rule_ids": ["rule-no-duplicates"]
    }
  ],
  "available_assertions": [
    {
      "assertion_id": "assert_order_recorded",
      "assertion_type": "STATE_MUTATION",
      "description": "Verify order is committed to database."
    }
  ],
  "observation_methods": [
    {
      "method_id": "obs_network_trace",
      "description": "Network delay monitor."
    }
  ],
  "seed": 42,
  "policy": {
    "max_cases": 10,
    "max_candidates_examined": 100
  }
}
```

**Response (HTTP 200 OK):**
```json
{
  "validation_scope": "STATIC_ONLY",
  "status": "GENERATED",
  "project_id": "proj-nexacart-qa",
  "selected_cases": [
    {
      "schema_version": "1.0.0",
      "project_id": "proj-nexacart-qa",
      "case_id": "case-3cf5b0c4",
      "case_family": "fam-create_order-timeout_or_disconnection-before_effect",
      "domain": "e-commerce",
      "task_id": "task-checkout-flow",
      "task_version": "1.0.0",
      "tool_id": "create_order",
      "tool_version": "1.0.0",
      "fixture_id": "fix-order-db",
      "fixture_version": "1.0.0",
      "adapter_id": "adapter-payment-order",
      "adapter_version": "1.0.0",
      "recovery_contract_id": "rec-standard-01",
      "recovery_contract_version": "1.0.0",
      "trigger": {
        "tool_id": "create_order",
        "call_occurrence": 1,
        "hook": "DURING_TRANSPORT"
      },
      "fault_family": "TIMEOUT_OR_DISCONNECTION",
      "effect_phase": "BEFORE_EFFECT",
      "payload": {
        "family": "TIMEOUT_OR_DISCONNECTION",
        "mode": "CONNECTION_TIMEOUT",
        "delay_ms": 100
      },
      "release_rule": {
        "mode": "SINGLE_CALL",
        "max_fault_occurrences": 1,
        "duration_seconds": null
      },
      "required_assertion_ids": ["assert_order_recorded"],
      "seed": 42,
      "caller_timeout_seconds": 2.0
    }
  ],
  "frozen_suite": {
    "schema_version": "1.0.0",
    "generator_version": "1.0.0",
    "suite_id": "suite-44b1c8ef28e20e6c",
    "content_digest": "44b1c8ef28e20e6c986cfa2b96e959ecbfd5ae8fc69be374f6645601c80c2f30",
    "project_id": "proj-nexacart-qa",
    "seed": 42,
    "policy": {
      "max_cases": 10,
      "max_candidates_examined": 100,
      "sampling_mode": "BOUNDARY_AND_REPRESENTATIVE"
    },
    "cases": [ ... ],
    "counters": {
      "examined_candidates": 4,
      "statically_valid_candidates": 4,
      "rejected_candidates": 0,
      "semantic_duplicates": 0,
      "unique_valid_candidates": 4,
      "selected_cases": 4
    },
    "truncated": false,
    "static_validation_status": "STATIC_VALID",
    "pending_checks": [
      "Runtime adapter tool endpoint and protocol verification pending.",
      "Runtime fault injector delivery for catalogue family pending.",
      "Agent invocation and recovery evaluation pending."
    ],
    "limitations": [
      "Static candidate generation only; cases are not executed or verified at runtime.",
      "Clean control qualification and fault exposure require live runtime execution.",
      "Recovery verdict is strictly null."
    ]
  },
  "counters": {
    "examined_candidates": 4,
    "statically_valid_candidates": 4,
    "rejected_candidates": 0,
    "semantic_duplicates": 0,
    "unique_valid_candidates": 4,
    "selected_cases": 4
  },
  "rejected_summaries": [],
  "skipped_summaries": [],
  "coverage_summary": {
    "fault_families_eligible": ["TIMEOUT_OR_DISCONNECTION"],
    "fault_families_covered": ["TIMEOUT_OR_DISCONNECTION"],
    "tools_eligible": ["create_order"],
    "tools_covered": ["create_order"],
    "candidate_population_denominator": 4,
    "is_truncated": false,
    "notes": ["Selected 4 cases across 1 fault families and 1 tools."]
  },
  "pending_checks": [
    "Runtime adapter tool endpoints and schemas unverified.",
    "Runtime fault injector delivery for non-timeout families not yet implemented.",
    "Agent invocation protocol and recovery evaluation deferred."
  ],
  "runtime_verified": false,
  "execution_ready": false,
  "recovery_verdict": null
}
```

### 5. Confirmed Defect Regressions Resolved in Phase 4
1. **Live CLI Exit Code**: Requesting `--live` when live integration prerequisites are missing returns exit code 2 with an explicit `[BLOCKED]` message.
2. **Database Separation Normalization**: `NexaCartPrismaFixtureManager._verify_not_qa_database()` normalizes driver prefixes, lowercase host, loopback resolution (`localhost` vs `127.0.0.1`), and default port (5432) to reject equivalent database identities before connecting.
3. **Settling Cleanup Verification**: `CLEANUP_VERIFIED` is only established when operations are settled (`in_flight_calls == 0`), new calls prevented (`_is_active == False`), observation evidence is available, and state fingerprints match across the settling period. Unsettled calls yield `CLEANUP_UNCERTAIN` and block fixture reuse.
4. **Transport Timeout Path Correlation**: The genuine interceptor path was verified against an ephemeral HTTP loopback server, correlating hook entry, tool occurrence, prevented forwarding, and caller-observed timeout.
5. **Evidence Linkage Prior to Export**: `save_evidence_artifact()` executes linkage verification before writing and rejects contradictory receipts.

### 6. Static-Only Boundaries and Deferred Scope
- **Not Executed**: Generating a frozen suite does not execute experiments, prove runtime readiness, or evaluate recovery.
- **Runtime Injector Delivery**: Only `TIMEOUT_OR_DISCONNECTION` before effect has a runtime injector implemented. Injectors for 5xx, 429, unavailability, malformed response, and `AFTER_COMMIT` remain pending.
- **Recovery Verdict**: Strictly `null` throughout Phase 4. Recovery scoring and C2 fact integration are deferred to subsequent phases.




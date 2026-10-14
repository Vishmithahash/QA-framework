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
    services/
        __init__.py
        validation.py       # Pure deterministic static capability and candidate case validator
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
- **Targeted Fault Family**: `TIMEOUT_OR_DISCONNECTION` exclusively.
- **Effect Phase**: `BEFORE_EFFECT` exclusively.
- **Release Rule**: Single-call one-shot release (`SINGLE_CALL` or `COUNT_BASED` with `max_fault_occurrences=1`).
- **Hook**: `DURING_TRANSPORT` or `PRE_TOOL_INVOCATION`.
- **Target Tool**: `create_order` (side-effecting domain tool).
- **Runtime Validation**: Rejects unsupported execution configurations (e.g. non-timeout families or `AFTER_COMMIT` phases) before execution rather than silently misbehaving.

### 3. Demonstration vs. Live Modes
- **Demonstration Mode (`TargetMode.FAKE_ADAPTER`, `CallerIdentity.SCRIPTED_CALLER`)**:
  - Uses `FakeNexaCartOrderToolAdapter` and `FakeNexaCartFixtureManager`.
  - Operates hermetically without external network or database dependencies.
  - Retries initiated by the scripted caller are labeled `RecoveryActor.SCRIPTED_CALLER` and never misattributed to agent decisions.
- **Live Target Mode (`TargetMode.LIVE_AUT`)**:
  - Connects to genuine application-under-test tools via `NexaCartHttpToolAdapter` and `NexaCartPrismaFixtureManager`.
  - **No Silent Fallback**: Live mode never falls back to fake adapters; missing configuration raises `IntegrationBlockedError`.
  - **Status: BLOCKED**. Inspection confirms that no NexaCart source code, Prisma schema, or OpenAPI definition currently exists in the repository.
- **Live Agent Mode (`CallerIdentity.ACTUAL_TESTED_AGENT`)**:
  - Requires domain tool routing through the C3 interceptor while leaving LLM-provider calls untouched.
  - **Status: BLOCKED**. No agent invocation protocol or tested agent implementation currently exists in the repository.

### 4. Prerequisites for Unblocking Live Execution
To unblock live integration without mock or fake fallbacks, the following prerequisites must be provisioned:
1. **Target OpenAPI/Tool Contract**: Authoritative endpoint definitions for `create_order` (request/response schemas, idempotency keys, error models).
2. **Dedicated Test Database**: `NEXACART_DATABASE_URL` pointing to an isolated test database (e.g. `postgresql://user:pass@localhost:5433/nexacart_test`). Must **never** point to the QA framework Neon database.
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
# Standard local paired-trial runner (demonstration mode)
.\.venv\Scripts\python.exe -m app.components.c3_robustness_recovery.runtime.runner --output-dir ./evidence_output

# Fast synthetic timeout mode
.\.venv\Scripts\python.exe -m app.components.c3_robustness_recovery.runtime.runner --synthetic --output-dir ./evidence_output

# Live AUT mode (will cleanly report BLOCKED with exact missing prerequisites)
.\.venv\Scripts\python.exe -m app.components.c3_robustness_recovery.runtime.runner --live
```

### 6. Exposure vs. Clean-Qualification Separation
- **Exposure Status (`CONFIRMED`, `NOT_TRIGGERED`, `EXPOSURE_UNKNOWN`)**:
  - Evaluated strictly from correlated fault trial receipts (`fault_injected=True`, `forwarded_to_target=False`, `caller_outcome=TIMEOUT`).
  - **Defect Fixed**: A failed clean control alone no longer forces `EXPOSURE_UNKNOWN`. Confirmed exposure coexists with failed clean qualification.
- **Clean Qualification (`true` / `false`)**:
  - Evaluates whether the normal control trial completed without error and performed the expected domain state mutation.
  - Failed clean controls are retained and never rerun until pass.
- **Interpretation Limitations**:
  - If clean qualification fails, the limitation is documented in `interpretation_limitations` while exposure remains truthfully `CONFIRMED`.
- **Recovery Verdict**: Strictly `null` (`None`) throughout Phase 3 (recovery evaluation is deferred).

### 7. Fixture Isolation, Reset, and Settling Limitations
- **Partitioned Namespaces**: Each trial uses an isolated partition namespace (`fixture_id_pair_id_clean` vs `fixture_id_pair_id_fault`), ensuring scoped resets never touch unrelated records.
- **Equivalence Verification**: Verifies identical initial logical state (record count, total amount, and state fingerprint) prior to injection.
- **Post-Trial Settling**: Observes the fixture after trial completion for a bounded settling period. If late in-flight mutations appear, `cleanup_status` is marked `CLEANUP_UNCERTAIN` and the fixture is marked unavailable for reuse (`fixture_reusable=False`).

### 8. Automated Test and Quality Suite

```powershell
# Run all tests (Foundation, Phase 2, and Phase 3 verification)
.\.venv\Scripts\python.exe -m pytest

# Run Ruff linter
.\.venv\Scripts\python.exe -m ruff check .

# Check formatting
.\.venv\Scripts\python.exe -m ruff format --check .

# Pip dependency consistency check
.\.venv\Scripts\python.exe -m pip check
```

### 9. Remaining C3 Backend Roadmap (Out of Scope for Phase 3)
- Automatic candidate fault case generation.
- Remaining fault families (`TRANSIENT_5XX_SERVER_ERROR`, `HTTP_429_RATE_LIMITING`, `TOOL_UNAVAILABILITY`, `MALFORMED_OR_TRUNCATED_RESPONSE`).
- `AFTER_COMMIT` post-commit fault injection and observation.
- C2 state-aware workflow assertion fact consumption.
- Shared Neon database persistence and Alembic migrations for test evidence.
- Research metrics and final LLM agent recovery evaluation scoring.



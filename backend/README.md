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

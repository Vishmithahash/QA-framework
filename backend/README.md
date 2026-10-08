# Backend Foundation - Agentic AI QA Framework

Backend foundation for the **Agentic AI-Based Software QA Framework for Testing Tool-Using LLM Applications**.

Provides a FastAPI backend with environment configuration, Neon PostgreSQL connectivity via SQLAlchemy 2.0 and psycopg 3, Alembic migrations, health check endpoints, and automated tests.

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

# Agentic AI QA Framework - Frontend Foundation

Shared frontend foundation for the **Agentic AI-Based Software QA Framework for Testing Tool-Using LLM Applications**.

This setup provides the shared architecture, design tokens, common navigation shell, routing namespaces, UI component library, environment configuration, in-memory project context, and API infrastructure so that all four research members can develop their individual components in parallel.

---

## 1. What the Common Foundation Includes

- **Development Tooling**: Vite 5 with React 18, TypeScript strict mode, ESLint, Prettier.
- **Application Shell**: Responsive blue-and-white theme layout featuring a collapsible sidebar, top navigation bar, main content container, keyboard accessibility, visible focus rings, and skip-to-content anchor.
- **Routing & Navigation**: React Router v6 with code-splitting (`React.lazy` + `Suspense`), global `ErrorBoundary`, and `NotFoundPage` (404).
- **Component Namespaces**: Dedicated route and folder structures for all 4 research components.
- **Shared UI Library**: Reusable presentation components adhering to CSS design tokens (`Button`, `PageHeader`, `Panel`, `EmptyState`, `LoadingState`, `ErrorState`, `StatusBadge`).
- **Environment & Configuration**: Centralized environment module reading `VITE_API_BASE_URL` and `VITE_API_TIMEOUT_MS`.
- **API Client Foundation**: Reusable typed JSON API client (`ApiClient`) supporting HTTP methods (`GET`, `POST`, `PUT`, `PATCH`, `DELETE`), custom headers, timeouts, cancellation (`AbortSignal`), and 204 No Content handling. Automatic retries are strictly disabled.
- **State & Data Caching**: TanStack Query Provider configured with non-retrying defaults and a project-scoped query key generator (`queryKeys.projectScoped`).
- **Active Project Context**: In-memory context (`ProjectContext`) displaying "No project selected" by default with selection/clearing primitives.

---

## 2. What Remains for Later Implementation

The following features are reserved for future implementation phases and are **not** part of this shared scaffolding:
- Tool-call correctness evaluation and parameter schema validation (C1).
- FSM/EFSM state modeling, workflow traversal, and state invariant checking (C2).
- Fault injection, paired trial execution, and recovery analysis (C3).
- Policy extraction, jailbreak prompt synthesis, and adversarial safety verification (C4).
- Candidate code patches, automated repair proposals, and sandbox execution.
- Actual backend database persistence for test runs, project CRUD, or report generation.
- Authentication or user access control.

---

## 3. Supported Versions & Installation

### Supported Runtime
- **Node.js**: `v20.0.0` or higher (verified on `v24.16.0`)
- **npm**: `v10.0.0` or higher (verified on `v11.13.0`)

### Installation Commands
Run all commands from the `frontend/` directory:

```bash
# Clean install using committed lockfile
npm ci
```

### Running Development Server

```bash
npm run dev
```
The Vite development server will start locally at [http://localhost:5173](http://localhost:5173). The frontend can run independently even if the backend is not running.

---

## 4. Environment Configuration

Copy the example file `.env.example` to `.env`:

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**macOS / Linux:**
```bash
cp .env.example .env
```

### Environment Variables
| Variable | Default Value | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | Base URL of the QA backend server |
| `VITE_API_TIMEOUT_MS` | `10000` | HTTP request timeout in milliseconds (10 seconds) |

> **Security Note**: Never store database credentials, LLM API keys, or private tokens in `VITE_*` variables. Vite bundles all `VITE_*` values directly into client-side JavaScript.

---

## 5. Verification & Build Commands

All quality and verification scripts can be executed via npm:

```bash
# 1. Typecheck TypeScript with strict checking
npm run typecheck

# 2. Run ESLint across source files
npm run lint

# 3. Check code formatting with Prettier
npm run format:check

# 4. Automatically format code with Prettier
npm run format

# 5. Production build
npm run build

# 6. Preview production build locally
npm run preview
```

---

## 6. Routes and Folder Responsibilities

### Folder Structure
```text
frontend/
├── .env.example            # Environment template
├── .gitignore              # Ignores dist/, node_modules/, .env
├── package.json            # Scripts and dependencies
├── package-lock.json       # Deterministic package lock
├── tsconfig.json           # Strict TypeScript configuration
├── vite.config.ts          # Vite build config with '@' path alias
├── src/
│   ├── app/                # App entry, providers, router, error boundary, context
│   │   ├── context/        # In-memory ProjectContext
│   │   ├── providers/      # AppProviders, QueryProvider
│   │   ├── router.tsx      # Route definitions and lazy loading
│   │   └── ErrorBoundary.tsx
│   ├── shared/             # Cross-cutting foundational modules
│   │   ├── api/            # ApiClient and query key factories
│   │   ├── config/         # Centralized env configuration
│   │   ├── hooks/          # Shared custom hooks
│   │   ├── layout/         # AppShell, navigation, NotFoundPage
│   │   ├── types/          # Shared interfaces (Project, Api, etc.)
│   │   └── ui/             # Reusable UI component library
│   ├── styles/             # tokens.css and global.css
│   └── features/           # Feature areas
│       ├── overview/       # Main dashboard overview
│       ├── projects/       # Projects management
│       ├── testing/        # Common testing workspace container & route tabs
│       ├── test-runs/      # Test run execution and monitoring
│       ├── reports/        # Reports list and detail
│       ├── settings/       # Framework settings
│       ├── tool-call-correctness/  # C1 component (Explainable Tool-Call Correctness)
│       ├── state-aware-workflow/   # C2 component (State-Aware Multi-Step Workflow)
│       ├── robustness-recovery/    # C3 component (Robustness and Failure Recovery)
│       └── policy-safety/          # C4 component (Policy-Aware Safety and Prompt-Injection)
```

### Route Table
| Route | Feature Area | Description |
|---|---|---|
| `/` | Overview | Dashboard and active project status |
| `/projects` | Projects | Project list scaffold |
| `/projects/:projectId` | Projects | Project detail scaffold |
| `/testing` | Testing Workspace | Common test container (guards on active project) |
| `/testing/tool-call-correctness/*` | Tool Calls | Explainable Tool-Call Correctness Testing |
| `/testing/state-aware-workflow/*` | Workflow & State | State-Aware Multi-Step Workflow Testing |
| `/testing/robustness-recovery/*` | Robustness & Recovery | Robustness and Failure Recovery Testing |
| `/testing/policy-safety/*` | Policy & Prompt Injection | Policy-Aware Safety and Prompt-Injection Testing |
| `/test-runs` | Test Runs | Run list scaffold |
| `/test-runs/:runId` | Test Runs | Run trace/evidence scaffold |
| `/reports` | Reports | Reports list scaffold |
| `/reports/:reportId` | Reports | Multi-component report detail |
| `/settings` | Settings | Framework configuration |
| `/components/*` | Compatibility | Legacy route redirects forwarding to `/testing/*` |
| `*` | Layout | 404 Not Found fallback |

---

## 7. How Each Team Member Starts Work

Each research component has a dedicated folder under `src/features/`:

| Component | Feature Folder | Member Area |
|---|---|---|
| **C1: Tool-Call Correctness** | `src/features/tool-call-correctness/` | Parameter validity, schema diagnostics |
| **C2: State-Aware Workflow** | `src/features/state-aware-workflow/` | Transition checks, EFSM/FSM verification |
| **C3: Robustness & Recovery** | `src/features/robustness-recovery/` | Fault injection, paired recovery trials |
| **C4: Policy Safety** | `src/features/policy-safety/` | Prompt injection, security policies |

### Testing Workflow Tab Mapping
The common testing workspace (`/testing`) maps workflow tabs directly to component page views:
- **Tool Calls** → Explainable Tool-Call Correctness Testing (`/testing/tool-call-correctness`)
- **Workflow & State** → State-Aware Multi-Step Workflow Testing (`/testing/state-aware-workflow`)
- **Robustness & Recovery** → Robustness and Failure Recovery Testing (`/testing/robustness-recovery`)
- **Policy & Prompt Injection** → Policy-Aware Safety and Prompt-Injection Testing (`/testing/policy-safety`)

Legacy component URLs (`/components/...`) automatically redirect to `/testing/...` while preserving nested subpaths and query parameters.

Inside your component folder, organize your code into the provided subdirectories:
- `pages/`: Route-level pages and sub-views.
- `components/`: UI elements internal to your component.
- `hooks/`: Component-specific React hooks.
- `services/`: API interaction functions calling `apiClient`.
- `types/`: TypeScript interfaces and domain models.

> **Team Isolation Rule**: Never import internal modules from another component's feature folder (e.g., C3 must not import from `features/c1_tool_call_correctness/`). If functionality is shared across components, place it in `src/shared/`.

---

## 8. Reusing Shared UI, API, and Project Context

### 1. Using Shared UI Components
```tsx
import { Button, PageHeader, Panel, EmptyState, StatusBadge } from '@/shared/ui';

export const MyComponent = () => (
  <div>
    <PageHeader 
      title="My Feature" 
      badge={<StatusBadge status="Active" variant="success" />} 
    />
    <Panel title="Results" elevated>
      <EmptyState title="No items" message="Run a test to see results." />
    </Panel>
    <Button variant="primary" onClick={() => {}}>Execute</Button>
  </div>
);
```

### 2. Using Active Project Context
```tsx
import { useProjectContext } from '@/app/context/ProjectContext';

export const MyComponent = () => {
  const { activeProject } = useProjectContext();
  return <div>Active Project: {activeProject?.name ?? 'None'}</div>;
};
```

### 3. Using the Shared API Client and Query Keys
```tsx
import { apiClient, queryKeys } from '@/shared/api';
import { useQuery } from '@tanstack/react-query';
import { useProjectContext } from '@/app/context/ProjectContext';

export function useMyComponentData() {
  const { activeProject } = useProjectContext();
  
  return useQuery({
    queryKey: queryKeys.projectScoped(activeProject?.id).component('my-component'),
    queryFn: ({ signal }) => 
      apiClient.get('/api/my-endpoint', { signal }),
    enabled: Boolean(activeProject?.id),
  });
}
```

---

## 9. Verifying Backend Contracts Before Integration

Before implementing endpoints or data fetching:
1. **Inspect Backend Routers**: Check `backend/app/main.py` and routers under `backend/app/` to identify registered route paths.
2. **Review OpenAPI Documentation**: When the backend server is running, visit [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) to verify request schemas, response codes, and query parameters.
3. **Handle Errors Gracefully**: Catch `ApiClientError` to display helpful messages rather than crashing the view.

---

## 10. CORS Requirements (Design Note)

- **Current Backend State**: The backend FastAPI application (`backend/app/main.py`) does not currently configure FastAPI `CORSMiddleware`.
- **Requirement for Future Integration**: When connecting the frontend development server (`http://localhost:5173`) to the backend (`http://127.0.0.1:8000`), the backend will require `CORSMiddleware` configured with `allow_origins=["http://localhost:5173"]`, `allow_credentials=True`, `allow_methods=["*"]`, and `allow_headers=["*"]`.
- Alternatively, Vite can configure a development proxy in `vite.config.ts`:
  ```ts
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  }
  ```
- No modifications have been made to the backend in this phase to preserve backend code integrity.

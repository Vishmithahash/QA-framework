import React from 'react';
import { NavLink, Outlet, useLocation, Navigate, Link } from 'react-router-dom';
import { useProjectContext } from '@/shared/hooks/useProjectContext';
import { PageHeader } from '@/shared/ui/PageHeader/PageHeader';
import { EmptyState } from '@/shared/ui/EmptyState/EmptyState';
import { Button } from '@/shared/ui/Button/Button';
import './TestingPage.css';

export const TestingPage: React.FC = () => {
  const { activeProject } = useProjectContext();
  const location = useLocation();

  if (!activeProject) {
    return (
      <div className="testing-workspace">
        <PageHeader
          title="Testing Workspace"
          description="Prepare, configure, and execute automated test suites for tool-using LLMs."
        />

        <EmptyState
          title="No project selected"
          message="Select a project to configure tests and review generated cases."
          icon="🧪"
          action={
            <Link to="/projects">
              <Button variant="primary">View Projects</Button>
            </Link>
          }
        />
      </div>
    );
  }

  // Redirect /testing root to default first tab if project is selected
  const isExactRoot = location.pathname === '/testing' || location.pathname === '/testing/';

  if (isExactRoot) {
    return <Navigate to="/testing/tool-call-correctness" replace />;
  }

  return (
    <div className="testing-workspace">
      <PageHeader
        title="Testing Workspace"
        description={`Configuring test suites for active project: ${activeProject.name}`}
      />

      <nav className="testing-tabs-nav" aria-label="Testing Components Navigation">
        <ul className="testing-tabs-list" role="tablist">
          <li role="presentation">
            <NavLink
              to="/testing/tool-call-correctness"
              role="tab"
              className={({ isActive }) => `testing-tab-link ${isActive ? 'active' : ''}`}
            >
              Tool Calls
            </NavLink>
          </li>
          <li role="presentation">
            <NavLink
              to="/testing/state-aware-workflow"
              role="tab"
              className={({ isActive }) => `testing-tab-link ${isActive ? 'active' : ''}`}
            >
              Workflow & State
            </NavLink>
          </li>
          <li role="presentation">
            <NavLink
              to="/testing/robustness-recovery"
              role="tab"
              className={({ isActive }) => `testing-tab-link ${isActive ? 'active' : ''}`}
            >
              Robustness & Recovery
            </NavLink>
          </li>
          <li role="presentation">
            <NavLink
              to="/testing/policy-safety"
              role="tab"
              className={({ isActive }) => `testing-tab-link ${isActive ? 'active' : ''}`}
            >
              Policy & Prompt Injection
            </NavLink>
          </li>
        </ul>
      </nav>

      <div className="testing-content-area">
        <Outlet />
      </div>
    </div>
  );
};

export default TestingPage;

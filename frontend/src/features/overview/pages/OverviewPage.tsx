import React from 'react';
import { Link } from 'react-router-dom';
import { useProjectContext } from '@/shared/hooks/useProjectContext';
import { PageHeader } from '@/shared/ui/PageHeader/PageHeader';
import { Panel } from '@/shared/ui/Panel/Panel';
import { EmptyState } from '@/shared/ui/EmptyState/EmptyState';
import { Button } from '@/shared/ui/Button/Button';
import { StatusBadge } from '@/shared/ui/StatusBadge/StatusBadge';

export const OverviewPage: React.FC = () => {
  const { activeProject } = useProjectContext();

  return (
    <div>
      <PageHeader
        title="Overview"
        description="Central status and navigation for the Agentic AI QA Framework."
      />

      {!activeProject ? (
        <Panel title="Project Workspace" elevated>
          <EmptyState
            title="Start with a project"
            message="Select a project to prepare agent tests and review results."
            icon="📁"
            action={
              <Link to="/projects">
                <Button variant="primary">View Projects</Button>
              </Link>
            }
          />
        </Panel>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
          <Panel
            title="Active Project"
            elevated
            headerAction={<StatusBadge status="Active" variant="success" />}
            footer={
              <Link to="/testing">
                <Button variant="primary">Open Testing</Button>
              </Link>
            }
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
              <h4
                style={{
                  fontSize: 'var(--font-size-lg)',
                  fontWeight: 'var(--font-weight-semibold)',
                }}
              >
                {activeProject.name}
              </h4>
              {activeProject.description && (
                <p style={{ color: 'var(--color-text-secondary)' }}>{activeProject.description}</p>
              )}
              <p style={{ fontSize: 'var(--font-size-sm)', color: 'var(--color-text-muted)' }}>
                Project selected. You can now prepare tests, inspect contracts, and follow
                executions in the testing workspace.
              </p>
            </div>
          </Panel>

          <Panel title="Recent Test Activity" elevated>
            <EmptyState
              title="No Test Executions"
              message="No test executions recorded yet for this project. Open testing to configure and run test suites."
              icon="⚡"
            />
          </Panel>
        </div>
      )}
    </div>
  );
};

export default OverviewPage;

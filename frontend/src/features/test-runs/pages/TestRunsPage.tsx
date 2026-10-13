import React from 'react';
import { PageHeader } from '@/shared/ui/PageHeader/PageHeader';
import { Panel } from '@/shared/ui/Panel/Panel';
import { EmptyState } from '@/shared/ui/EmptyState/EmptyState';

export const TestRunsPage: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Test Runs"
        description="Monitor evaluation executions across research components."
      />

      <Panel title="Recent Test Runs" elevated>
        <EmptyState
          title="No Test Runs Recorded"
          message="Execution runs and live status tracking will be displayed here once test execution pipelines are integrated."
          icon="⚡"
        />
      </Panel>
    </div>
  );
};

export default TestRunsPage;

import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { PageHeader } from '@/shared/ui/PageHeader/PageHeader';
import { Panel } from '@/shared/ui/Panel/Panel';
import { EmptyState } from '@/shared/ui/EmptyState/EmptyState';
import { Button } from '@/shared/ui/Button/Button';

export const TestRunDetailPage: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();

  return (
    <div>
      <PageHeader
        title={`Test Run: ${runId ?? 'Unknown'}`}
        description="Execution trace, telemetry, and component evaluation evidence."
        actions={
          <Link to="/test-runs">
            <Button variant="secondary">Back to Test Runs</Button>
          </Link>
        }
      />

      <Panel title="Run Overview" elevated>
        <EmptyState
          title="Run Detail Scaffold"
          message={`Viewing placeholder detail for test run identifier '${runId}'. Execution data and evidence inspection will be connected in a later phase.`}
          icon="⚡"
        />
      </Panel>
    </div>
  );
};

export default TestRunDetailPage;

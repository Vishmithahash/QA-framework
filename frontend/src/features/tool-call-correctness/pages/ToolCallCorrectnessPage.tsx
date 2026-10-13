import React from 'react';
import { PageHeader } from '@/shared/ui/PageHeader/PageHeader';
import { Panel } from '@/shared/ui/Panel/Panel';
import { EmptyState } from '@/shared/ui/EmptyState/EmptyState';
import { StatusBadge } from '@/shared/ui/StatusBadge/StatusBadge';

export const ToolCallCorrectnessPage: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Explainable Tool-Call Correctness Testing"
        description="Research Component 1: Evaluation of tool parameter validity, schema conformity, and execution correctness."
        badge={<StatusBadge status="Scaffold" variant="neutral" />}
      />

      <Panel title="Component Workspace" elevated>
        <EmptyState
          title="Explainable Tool-Call Correctness Testing"
          message="Component implementation will be added in a later phase."
          icon="🧩"
        />
      </Panel>
    </div>
  );
};

export default ToolCallCorrectnessPage;

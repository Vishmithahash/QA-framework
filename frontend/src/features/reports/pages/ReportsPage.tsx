import React from 'react';
import { PageHeader } from '@/shared/ui/PageHeader/PageHeader';
import { Panel } from '@/shared/ui/Panel/Panel';
import { EmptyState } from '@/shared/ui/EmptyState/EmptyState';

export const ReportsPage: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Integrated Reports"
        description="Comprehensive analysis reports cross-referencing all evaluation components."
      />

      <Panel title="Available Reports" elevated>
        <EmptyState
          title="No Reports Generated"
          message="Integrated cross-component analysis and report exports will be available in later phases."
          icon="📈"
        />
      </Panel>
    </div>
  );
};

export default ReportsPage;

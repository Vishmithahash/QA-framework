import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { PageHeader } from '@/shared/ui/PageHeader/PageHeader';
import { Panel } from '@/shared/ui/Panel/Panel';
import { EmptyState } from '@/shared/ui/EmptyState/EmptyState';
import { Button } from '@/shared/ui/Button/Button';

export const ReportDetailPage: React.FC = () => {
  const { reportId } = useParams<{ reportId: string }>();

  return (
    <div>
      <PageHeader
        title={`Report: ${reportId ?? 'Unknown'}`}
        description="Detailed multi-component evaluation findings and defect analysis."
        actions={
          <Link to="/reports">
            <Button variant="secondary">Back to Reports</Button>
          </Link>
        }
      />

      <Panel title="Report Overview" elevated>
        <EmptyState
          title="Report Detail Scaffold"
          message={`Viewing placeholder detail for report identifier '${reportId}'. Multi-component report views will be implemented in a later phase.`}
          icon="📊"
        />
      </Panel>
    </div>
  );
};

export default ReportDetailPage;

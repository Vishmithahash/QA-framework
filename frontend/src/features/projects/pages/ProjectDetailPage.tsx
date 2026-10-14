import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { PageHeader } from '@/shared/ui/PageHeader/PageHeader';
import { Panel } from '@/shared/ui/Panel/Panel';
import { EmptyState } from '@/shared/ui/EmptyState/EmptyState';
import { Button } from '@/shared/ui/Button/Button';

export const ProjectDetailPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();

  return (
    <div>
      <PageHeader
        title={`Project: ${projectId ?? 'Unknown'}`}
        description="Detailed view and configuration for the selected project."
        actions={
          <Link to="/projects">
            <Button variant="secondary">Back to Projects</Button>
          </Link>
        }
      />

      <Panel title="Project Details" elevated>
        <EmptyState
          title="Project Detail Scaffold"
          message={`Viewing placeholder detail for project identifier '${projectId}'. Full project management will be implemented in a later phase.`}
          icon="📂"
        />
      </Panel>
    </div>
  );
};

export default ProjectDetailPage;

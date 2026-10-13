import React from 'react';
import { PageHeader } from '@/shared/ui/PageHeader/PageHeader';
import { Panel } from '@/shared/ui/Panel/Panel';
import { EmptyState } from '@/shared/ui/EmptyState/EmptyState';

export const ProjectsPage: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Projects"
        description="Manage projects under test and active workspace scope."
      />

      <Panel title="Configured Projects" elevated>
        <EmptyState
          title="No Projects Configured"
          message="Project management and persistent storage will be integrated once backend schemas are connected."
          icon="📁"
        />
      </Panel>
    </div>
  );
};

export default ProjectsPage;

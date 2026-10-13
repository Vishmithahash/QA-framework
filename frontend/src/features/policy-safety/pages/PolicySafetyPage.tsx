import React from 'react';
import { PageHeader } from '@/shared/ui/PageHeader/PageHeader';
import { Panel } from '@/shared/ui/Panel/Panel';
import { EmptyState } from '@/shared/ui/EmptyState/EmptyState';
import { StatusBadge } from '@/shared/ui/StatusBadge/StatusBadge';

export const PolicySafetyPage: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Policy-Aware Safety and Prompt-Injection Testing"
        description="Research Component 4: Security policy evaluation, jailbreak resistance, and adversarial prompt detection."
        badge={<StatusBadge status="Scaffold" variant="neutral" />}
      />

      <Panel title="Component Workspace" elevated>
        <EmptyState
          title="Policy-Aware Safety and Prompt-Injection Testing"
          message="Component implementation will be added in a later phase."
          icon="🔒"
        />
      </Panel>
    </div>
  );
};

export default PolicySafetyPage;

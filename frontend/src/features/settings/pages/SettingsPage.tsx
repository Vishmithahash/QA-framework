import React from 'react';
import { PageHeader } from '@/shared/ui/PageHeader/PageHeader';
import { Panel } from '@/shared/ui/Panel/Panel';
import { env } from '@/shared/config/env';

export const SettingsPage: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Settings"
        description="Framework runtime parameters and frontend environment configuration."
      />

      <Panel title="Frontend Environment Foundation" elevated>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <p style={{ color: 'var(--color-text-secondary)' }}>
            The frontend uses centralized environment variables configured via <code>.env</code> or
            defaults.
          </p>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '200px 1fr',
              gap: 'var(--space-2)',
              fontSize: 'var(--font-size-sm)',
            }}
          >
            <strong>API Base URL:</strong>
            <code>{env.apiBaseUrl}</code>
            <strong>API Timeout:</strong>
            <code>{env.apiTimeoutMs} ms</code>
          </div>
        </div>
      </Panel>
    </div>
  );
};

export default SettingsPage;

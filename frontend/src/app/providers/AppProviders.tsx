import React, { type ReactNode } from 'react';
import { QueryProvider } from './QueryProvider';
import { ProjectProvider } from '@/app/context/ProjectContext';

interface AppProvidersProps {
  children: ReactNode;
}

export const AppProviders: React.FC<AppProvidersProps> = ({ children }) => {
  return (
    <QueryProvider>
      <ProjectProvider>{children}</ProjectProvider>
    </QueryProvider>
  );
};

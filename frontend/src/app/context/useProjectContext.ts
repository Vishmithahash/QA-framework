import { useContext } from 'react';
import { ProjectContext, type ProjectContextValue } from './projectContextInstance';

export function useProjectContext(): ProjectContextValue {
  const context = useContext(ProjectContext);
  if (!context) {
    throw new Error('useProjectContext must be used within a ProjectProvider');
  }
  return context;
}

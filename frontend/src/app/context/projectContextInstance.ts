import { createContext } from 'react';
import type { Project } from '@/shared/types/project';

export interface ProjectContextValue {
  activeProject: Project | null;
  setActiveProject: (project: Project | null) => void;
  clearActiveProject: () => void;
}

export const ProjectContext = createContext<ProjectContextValue | undefined>(undefined);

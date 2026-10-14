import React, { useState, useMemo, type ReactNode } from 'react';
import type { Project } from '@/shared/types/project';
import { ProjectContext } from './projectContextInstance';

export interface ProjectProviderProps {
  children: ReactNode;
  initialProject?: Project | null;
}

export const ProjectProvider: React.FC<ProjectProviderProps> = ({
  children,
  initialProject = null,
}) => {
  const [activeProject, setActiveProject] = useState<Project | null>(initialProject);

  const clearActiveProject = () => {
    setActiveProject(null);
  };

  const value = useMemo(
    () => ({
      activeProject,
      setActiveProject,
      clearActiveProject,
    }),
    [activeProject]
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
};

export default ProjectProvider;

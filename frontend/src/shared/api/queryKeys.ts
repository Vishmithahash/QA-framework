/**
 * Query key factory helper for scoping TanStack Query cache keys by project.
 * Ensures isolation across projects and prevents cross-project cache contamination.
 */

export const queryKeys = {
  // Global / Root keys
  allProjects: () => ['projects'] as const,
  projectDetail: (projectId: string) => ['projects', projectId] as const,

  // Scoped by active project
  projectScoped: (projectId: string | null | undefined) => {
    const scope = projectId ?? 'no-project';
    return {
      all: ['project-scope', scope] as const,
      runs: () => ['project-scope', scope, 'test-runs'] as const,
      runDetail: (runId: string) => ['project-scope', scope, 'test-runs', runId] as const,
      reports: () => ['project-scope', scope, 'reports'] as const,
      reportDetail: (reportId: string) => ['project-scope', scope, 'reports', reportId] as const,
      component: (componentKey: string) =>
        ['project-scope', scope, 'component', componentKey] as const,
    };
  },
};

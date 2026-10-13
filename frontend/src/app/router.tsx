import React, { lazy, Suspense } from 'react';
import { createBrowserRouter } from 'react-router-dom';
import { AppShell } from '@/shared/layout/AppShell';
import { NotFoundPage } from '@/shared/layout/NotFoundPage';
import { LoadingState } from '@/shared/ui/LoadingState/LoadingState';
import { ErrorBoundary } from '@/app/ErrorBoundary';

// Helper for lazy loading with Suspense and ErrorBoundary
function withSuspense(Component: React.ComponentType) {
  return (
    <ErrorBoundary>
      <Suspense fallback={<LoadingState message="Loading page..." />}>
        <Component />
      </Suspense>
    </ErrorBoundary>
  );
}

import { LegacyComponentRedirect } from './LegacyComponentRedirect';

// Lazy loaded page components
const OverviewPage = lazy(() => import('@/features/overview/pages/OverviewPage'));
const ProjectsPage = lazy(() => import('@/features/projects/pages/ProjectsPage'));
const ProjectDetailPage = lazy(() => import('@/features/projects/pages/ProjectDetailPage'));
const TestingPage = lazy(() => import('@/features/testing/pages/TestingPage'));
const TestRunsPage = lazy(() => import('@/features/test-runs/pages/TestRunsPage'));
const TestRunDetailPage = lazy(() => import('@/features/test-runs/pages/TestRunDetailPage'));
const ReportsPage = lazy(() => import('@/features/reports/pages/ReportsPage'));
const ReportDetailPage = lazy(() => import('@/features/reports/pages/ReportDetailPage'));
const SettingsPage = lazy(() => import('@/features/settings/pages/SettingsPage'));

// Research component pages
const ToolCallCorrectnessPage = lazy(
  () => import('@/features/tool-call-correctness/pages/ToolCallCorrectnessPage')
);
const StateAwareWorkflowPage = lazy(
  () => import('@/features/state-aware-workflow/pages/StateAwareWorkflowPage')
);
const RobustnessRecoveryPage = lazy(
  () => import('@/features/robustness-recovery/pages/RobustnessRecoveryPage')
);
const PolicySafetyPage = lazy(() => import('@/features/policy-safety/pages/PolicySafetyPage'));

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    errorElement: (
      <AppShell>
        <NotFoundPage />
      </AppShell>
    ),
    children: [
      {
        index: true,
        element: withSuspense(OverviewPage),
      },
      {
        path: 'projects',
        children: [
          {
            index: true,
            element: withSuspense(ProjectsPage),
          },
          {
            path: ':projectId',
            element: withSuspense(ProjectDetailPage),
          },
        ],
      },
      {
        path: 'testing',
        element: withSuspense(TestingPage),
        children: [
          {
            path: 'tool-call-correctness',
            children: [
              {
                index: true,
                element: withSuspense(ToolCallCorrectnessPage),
              },
              {
                path: '*',
                element: withSuspense(ToolCallCorrectnessPage),
              },
            ],
          },
          {
            path: 'state-aware-workflow',
            children: [
              {
                index: true,
                element: withSuspense(StateAwareWorkflowPage),
              },
              {
                path: '*',
                element: withSuspense(StateAwareWorkflowPage),
              },
            ],
          },
          {
            path: 'robustness-recovery',
            children: [
              {
                index: true,
                element: withSuspense(RobustnessRecoveryPage),
              },
              {
                path: '*',
                element: withSuspense(RobustnessRecoveryPage),
              },
            ],
          },
          {
            path: 'policy-safety',
            children: [
              {
                index: true,
                element: withSuspense(PolicySafetyPage),
              },
              {
                path: '*',
                element: withSuspense(PolicySafetyPage),
              },
            ],
          },
        ],
      },
      {
        path: 'test-runs',
        children: [
          {
            index: true,
            element: withSuspense(TestRunsPage),
          },
          {
            path: ':runId',
            element: withSuspense(TestRunDetailPage),
          },
        ],
      },
      {
        path: 'reports',
        children: [
          {
            index: true,
            element: withSuspense(ReportsPage),
          },
          {
            path: ':reportId',
            element: withSuspense(ReportDetailPage),
          },
        ],
      },
      {
        path: 'settings',
        element: withSuspense(SettingsPage),
      },
      // Backward Compatibility: Redirect legacy /components/... routes to /testing/...
      {
        path: 'components/tool-call-correctness/*',
        element: <LegacyComponentRedirect target="tool-call-correctness" />,
      },
      {
        path: 'components/state-aware-workflow/*',
        element: <LegacyComponentRedirect target="state-aware-workflow" />,
      },
      {
        path: 'components/robustness-recovery/*',
        element: <LegacyComponentRedirect target="robustness-recovery" />,
      },
      {
        path: 'components/policy-safety/*',
        element: <LegacyComponentRedirect target="policy-safety" />,
      },
      // 404 handler inside layout
      {
        path: '*',
        element: <NotFoundPage />,
      },
    ],
  },
]);

export default router;

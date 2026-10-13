import { QueryClient } from '@tanstack/react-query';

// Shared QueryClient configured with strict non-retrying defaults
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false, // Explicitly disable automatic retries
      refetchOnWindowFocus: false, // Avoid unexpected re-fetching on tab switches
      staleTime: 0,
    },
    mutations: {
      retry: false, // Never automatically repeat mutating actions / test run initiations
    },
  },
});

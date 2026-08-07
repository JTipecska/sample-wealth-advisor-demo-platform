import { createRootRoute, Outlet } from '@tanstack/react-router';
import { ImprovedChatWidget } from '../components/ImprovedChatWidget';
import CognitoAuth from '../components/CognitoAuth';
import ApiProvider from '../components/ApiProvider';
import RuntimeConfigProvider from '../components/RuntimeConfig';
import {
  QueryClient,
  QueryClientProvider,
  keepPreviousData,
} from '@tanstack/react-query';

// Stale-while-revalidate defaults: serve cached data instantly, then check for
// new data in the background and swap it in only once it has loaded — so
// revisiting a page never drops to a skeleton when we already have data.
// - staleTime 5m: don't re-hit the API on every mount within the window
// - gcTime 24h: keep cached data around across navigation (default 5m evicted
//   it, which is why revisits showed the loading screen again)
// - placeholderData keepPreviousData: while a query key changes (client switch,
//   pagination) keep showing the previous data instead of a spinner
// - refetchOnWindowFocus off: no surprise refetch/flash when tabbing back
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 24 * 60 * 60 * 1000,
      refetchOnWindowFocus: false,
      placeholderData: keepPreviousData,
      retry: 1,
    },
  },
});

export const Route = createRootRoute({
  component: () => (
    <QueryClientProvider client={queryClient}>
      <RuntimeConfigProvider>
        <CognitoAuth>
          <ApiProvider>
            <Outlet />
            <ImprovedChatWidget />
          </ApiProvider>
        </CognitoAuth>
      </RuntimeConfigProvider>
    </QueryClientProvider>
  ),
});

import { useRuntimeConfig } from '../../hooks/useRuntimeConfig';
import { useAuth } from 'react-oidc-context';
import { useCallback } from 'react';
import type { DDReport, HITLFlag, Portfolio, Session } from './types';

export function useDDApi() {
  const config = useRuntimeConfig();
  const auth = useAuth();
  const baseUrl: string = (config as any).apis?.PortfolioDDApi ?? 'http://localhost:8092';

  const headers = useCallback(
    () => ({
      'Content-Type': 'application/json',
      ...(auth.user?.id_token ? { Authorization: `Bearer ${auth.user.id_token}` } : {}),
    }),
    [auth.user?.id_token],
  );

  const listPortfolios = useCallback(async (): Promise<Portfolio[]> => {
    const r = await fetch(`${baseUrl}/dd/portfolios`, { headers: headers() });
    const d = await r.json();
    return d.portfolios ?? [];
  }, [baseUrl, headers]);

  const startReview = useCallback(
    async (portfolioId: string): Promise<Session> => {
      const r = await fetch(`${baseUrl}/dd/sessions`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ portfolio_id: portfolioId, initiated_by: auth.user?.profile?.email ?? 'demo' }),
      });
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    },
    [baseUrl, headers, auth.user?.profile?.email],
  );

  const getSession = useCallback(
    async (sessionId: string): Promise<Session> => {
      const r = await fetch(`${baseUrl}/dd/sessions/${sessionId}`, { headers: headers() });
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    },
    [baseUrl, headers],
  );

  const getReport = useCallback(
    async (sessionId: string): Promise<DDReport> => {
      const r = await fetch(`${baseUrl}/dd/sessions/${sessionId}/report`, { headers: headers() });
      if (!r.ok) throw new Error(await r.text());
      return r.json();
    },
    [baseUrl, headers],
  );

  const listFlags = useCallback(
    async (sessionId: string): Promise<HITLFlag[]> => {
      const r = await fetch(`${baseUrl}/dd/sessions/${sessionId}/hitl`, { headers: headers() });
      const d = await r.json();
      return d.flags ?? [];
    },
    [baseUrl, headers],
  );

  const resolveFlag = useCallback(
    async (sessionId: string, flagId: string, resolution: string, notes: string): Promise<void> => {
      await fetch(`${baseUrl}/dd/sessions/${sessionId}/hitl/${flagId}/resolve`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ resolution, reviewer_notes: notes, reviewer: auth.user?.profile?.email ?? '' }),
      });
    },
    [baseUrl, headers, auth.user?.profile?.email],
  );

  const streamProgress = useCallback(
    (sessionId: string) => new EventSource(`${baseUrl}/dd/sessions/${sessionId}/stream`),
    [baseUrl],
  );

  return { listPortfolios, startReview, getSession, getReport, listFlags, resolveFlag, streamProgress };
}

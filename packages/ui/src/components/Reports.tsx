import { useState, useEffect, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { PageLayout } from './PageLayout';
import { useApiClient } from '../hooks/useApiClient';
import { useRuntimeConfig } from '../hooks/useRuntimeConfig';
import { useAuth } from 'react-oidc-context';
import type { Api } from '../generated/api/client.gen';

function ReportCell({
  clientId,
  hasReport,
  api,
  apiUrl,
  token,
}: {
  clientId: string;
  hasReport: boolean;
  api: Api;
  apiUrl: string;
  token: string | undefined;
}) {
  const [state, setState] = useState<
    'idle' | 'loading' | 'generating' | 'error'
  >('idle');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(
    () => () => {
      if (pollRef.current) clearInterval(pollRef.current);
    },
    [],
  );

  const handleViewOrGenerate = () => {
    setState('loading');
    api
      .clientReport({ clientId })
      .then((r) => {
        if (r.status === 'complete' && r.presignedUrl) {
          window.open(r.presignedUrl, '_blank');
          setState('idle');
        } else {
          triggerGeneration();
        }
      })
      .catch(() => {
        triggerGeneration();
      });
  };

  const triggerGeneration = () => {
    setState('generating');
    fetch(`${apiUrl}clients/${clientId}/report/generate`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => r.json())
      .then((result) => {
        if (result.presigned_url) {
          window.open(result.presigned_url, '_blank');
          setState('idle');
        } else {
          pollForReport();
        }
      })
      .catch(() => setState('error'));
  };

  const pollForReport = () => {
    let attempts = 0;
    pollRef.current = setInterval(() => {
      attempts++;
      if (attempts > 30) {
        if (pollRef.current) clearInterval(pollRef.current);
        setState('error');
        return;
      }
      api
        .clientReport({ clientId })
        .then((r) => {
          if (r.presignedUrl) {
            if (pollRef.current) clearInterval(pollRef.current);
            window.open(r.presignedUrl, '_blank');
            setState('idle');
          }
        })
        .catch(() => undefined);
    }, 3000);
  };

  if (state === 'loading')
    return <span className="text-xs text-gray-400">Checking...</span>;
  if (state === 'generating')
    return (
      <span className="text-xs text-amber-600 animate-pulse">
        Generating...
      </span>
    );
  if (state === 'error')
    return (
      <button
        onClick={handleViewOrGenerate}
        className="text-xs text-red-500 hover:text-red-700 font-medium"
      >
        Retry
      </button>
    );
  return (
    <button
      onClick={handleViewOrGenerate}
      className={`text-xs font-medium ${hasReport ? 'text-blue-600 hover:text-blue-700' : 'text-amber-600 hover:text-amber-700'}`}
    >
      {hasReport ? 'View Report' : 'Generate Report'}
    </button>
  );
}

interface Client {
  clientId: string;
  customerName: string;
  segment: string;
  aum: number;
  ytdPerf: number;
  nextBestAction?: string | null;
}

export function ReportsPage() {
  const navigate = useNavigate();
  const api = useApiClient();
  const runtimeConfig = useRuntimeConfig();
  const auth = useAuth();
  const [clients, setClients] = useState<Client[]>([]);
  const [clientsWithReports, setClientsWithReports] = useState<Set<string>>(
    new Set(),
  );
  const [loading, setLoading] = useState(true);

  const apiUrl = runtimeConfig?.apis?.Api ?? '';
  const token = auth.user?.id_token;

  useEffect(() => {
    Promise.all([
      api.clients({ limit: 100 }),
      fetch(`${apiUrl}reports/summary`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      }).then((r) => (r.ok ? r.json() : { clients_with_reports: [] })),
    ])
      .then(([clientsRes, summaryRes]) => {
        setClients(clientsRes.clients || []);
        setClientsWithReports(
          new Set(summaryRes.clients_with_reports || []),
        );
      })
      .catch(() => setClients([]))
      .finally(() => setLoading(false));
  }, [api, apiUrl, token]);

  const totalClients = clients.length;
  const reportsAvailable = clientsWithReports.size;
  const pendingGeneration = Math.max(0, totalClients - reportsAvailable);

  return (
    <PageLayout title="Reports">
      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm text-gray-500">Total Clients</p>
          <p className="text-3xl font-bold mt-1 text-blue-600">
            {totalClients}
          </p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm text-gray-500">Reports Available</p>
          <p className="text-3xl font-bold mt-1 text-green-600">
            {reportsAvailable}
          </p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm text-gray-500">Pending Generation</p>
          <p className="text-3xl font-bold mt-1 text-amber-600">
            {pendingGeneration}
          </p>
        </div>
      </div>

      {/* Client reports table */}
      <div className="bg-white rounded-xl border border-gray-200">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-800">Client Reports</h2>
        </div>
        {loading ? (
          <div className="px-6 py-12 text-center text-gray-400">
            Loading clients...
          </div>
        ) : clients.length === 0 ? (
          <div className="px-6 py-12 text-center text-gray-400">
            No clients found.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 text-xs uppercase tracking-wider border-b border-gray-100">
                <th className="px-6 py-3">Customer Name</th>
                <th className="px-6 py-3">Segment</th>
                <th className="px-6 py-3">AUM</th>
                <th className="px-6 py-3">YTD Perf.</th>
                <th className="px-6 py-3">Report</th>
                <th className="px-6 py-3">Next Best Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {clients.map((c) => (
                <tr
                  key={c.clientId}
                  className="hover:bg-gray-50 transition-colors"
                >
                  <td className="px-6 py-4">
                    <button
                      onClick={() =>
                        navigate({
                          to: '/clients/$clientId',
                          params: { clientId: c.clientId },
                        })
                      }
                      className="text-blue-600 hover:underline font-medium"
                    >
                      {c.customerName}
                    </button>
                  </td>
                  <td className="px-6 py-4 text-gray-600">
                    <span className="px-2 py-1 rounded-full text-xs bg-gray-100">
                      {c.segment}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-gray-900 font-medium">
                    ${(c.aum / 1000000).toFixed(2)}M
                  </td>
                  <td className="px-6 py-4">
                    <span
                      className={
                        c.ytdPerf >= 0 ? 'text-green-600' : 'text-red-600'
                      }
                    >
                      {c.ytdPerf >= 0 ? '+' : ''}
                      {c.ytdPerf?.toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <ReportCell
                      clientId={c.clientId}
                      hasReport={clientsWithReports.has(c.clientId)}
                      api={api}
                      apiUrl={apiUrl}
                      token={token}
                    />
                  </td>
                  <td className="px-6 py-4 text-gray-500 text-xs max-w-[200px] truncate">
                    {c.nextBestAction || '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </PageLayout>
  );
}

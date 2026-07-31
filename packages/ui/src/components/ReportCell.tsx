import { useEffect, useRef, useState } from 'react';
import { useRuntimeConfig } from '../hooks/useRuntimeConfig';
import { useAuth } from 'react-oidc-context';
import type { Api } from '../generated/api/client.gen';

interface ReportCellProps {
  clientId: string;
  api: Api;
  hasReport?: boolean;
}

export function ReportCell({
  clientId,
  api,
  hasReport = true,
}: ReportCellProps) {
  const runtimeConfig = useRuntimeConfig();
  const auth = useAuth();
  const apiUrl = runtimeConfig?.apis?.Api ?? '';
  const token = auth.user?.id_token;

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
    fetch(`${apiUrl.replace(/\/$/, '')}/clients/${clientId}/report/generate`, {
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

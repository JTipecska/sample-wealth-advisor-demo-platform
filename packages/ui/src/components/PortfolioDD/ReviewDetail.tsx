import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import { PageLayout } from '../PageLayout';
import { useDDApi } from './useDDApi';
import type { Session, ProgressEvent, HITLFlag } from './types';

const RAG_DOT: Record<string, string> = {
  green: 'bg-green-500',
  amber: 'bg-yellow-400',
  red: 'bg-red-500',
  grey: 'bg-gray-300',
};

const CATEGORY_LABELS: Record<string, string> = {
  investment_process: 'Investment Process',
  risk_operations: 'Risk & Operations',
  compliance_esg: 'Compliance & ESG',
  commercial: 'Commercial',
};

export function ReviewDetail() {
  const { reviewId } = useParams({ from: '/portfolio-dd/$reviewId' });
  const navigate = useNavigate();
  const api = useDDApi();

  const [session, setSession] = useState<Session | null>(null);
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [flags, setFlags] = useState<HITLFlag[]>([]);
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const [resolveNotes, setResolveNotes] = useState('');
  const feedRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    api.getSession(reviewId).then(setSession).catch(() => {});
  }, [reviewId]);

  useEffect(() => {
    if (!reviewId) return;
    const es = api.streamProgress(reviewId);
    esRef.current = es;

    es.addEventListener('pipeline_started', (e) => {
      const data: ProgressEvent = JSON.parse((e as MessageEvent).data);
      setEvents((prev) => [...prev, data]);
    });

    es.addEventListener('criterion_complete', (e) => {
      const data: ProgressEvent = JSON.parse((e as MessageEvent).data);
      setEvents((prev) => [...prev, data]);
    });

    es.addEventListener('hitl_flag', (e) => {
      const data: ProgressEvent = JSON.parse((e as MessageEvent).data);
      setEvents((prev) => [...prev, data]);
      setFlags((prev) => [...prev, {
        flag_id: (data.data?.flag_id as string) ?? '',
        reason: data.message,
        status: 'pending',
        reviewer_notes: '',
      }]);
    });

    es.addEventListener('report_ready', (e) => {
      const data: ProgressEvent = JSON.parse((e as MessageEvent).data);
      setEvents((prev) => [...prev, data]);
      api.getSession(reviewId).then(setSession).catch(() => {});
      api.listFlags(reviewId).then(setFlags).catch(() => {});
    });

    es.addEventListener('error', (e) => {
      const data: ProgressEvent = JSON.parse((e as MessageEvent).data);
      setEvents((prev) => [...prev, data]);
    });

    es.addEventListener('done', () => {
      es.close();
    });

    return () => {
      es.close();
    };
  }, [reviewId]);

  useEffect(() => {
    feedRef.current?.scrollTo({ top: feedRef.current.scrollHeight, behavior: 'smooth' });
  }, [events]);

  const handleResolve = async (flagId: string, resolution: string) => {
    await api.resolveFlag(reviewId, flagId, resolution, resolveNotes);
    setFlags((prev) =>
      prev.map((f) => f.flag_id === flagId ? { ...f, status: resolution as HITLFlag['status'], reviewer_notes: resolveNotes } : f),
    );
    setResolvingId(null);
    setResolveNotes('');
  };

  const assessments = session ? [] : []; // populated from report page

  return (
    <PageLayout
      title={session?.portfolio_name ?? 'Due Diligence Review'}
      headerContent={
        session?.status === 'complete' ? (
          <button
            onClick={() => navigate({ to: '/portfolio-dd/$reviewId/report', params: { reviewId } })}
            className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700"
          >
            View Report
          </button>
        ) : undefined
      }
    >
      <div className="grid grid-cols-3 gap-6">
        {/* Left: session meta + HITL flags */}
        <div className="col-span-1 space-y-4">
          {/* Session card */}
          <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-3">
            <h3 className="font-semibold text-gray-800 text-sm">Session Info</h3>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between">
                <dt className="text-gray-500">Status</dt>
                <dd>
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                    session?.status === 'complete' ? 'bg-green-100 text-green-700' :
                    session?.status === 'in_progress' ? 'bg-blue-100 text-blue-700' :
                    session?.status === 'failed' ? 'bg-red-100 text-red-700' :
                    'bg-gray-100 text-gray-600'
                  }`}>{session?.status ?? '—'}</span>
                </dd>
              </div>
              {session?.overall_score != null && (
                <div className="flex justify-between">
                  <dt className="text-gray-500">Score</dt>
                  <dd className="font-semibold">{session.overall_score.toFixed(1)}/10</dd>
                </div>
              )}
              {session?.recommendation && (
                <div className="flex justify-between">
                  <dt className="text-gray-500">Recommendation</dt>
                  <dd>
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      session.recommendation === 'APPROVE' ? 'bg-green-100 text-green-700' :
                      session.recommendation === 'REJECT' ? 'bg-red-100 text-red-700' :
                      'bg-amber-100 text-amber-700'
                    }`}>{session.recommendation}</span>
                  </dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-gray-500">Started</dt>
                <dd className="text-gray-700">{session ? new Date(session.started_at).toLocaleString() : '—'}</dd>
              </div>
            </dl>
          </div>

          {/* HITL Flags */}
          {flags.length > 0 && (
            <div className="bg-white rounded-xl border border-amber-200 p-5 space-y-3">
              <h3 className="font-semibold text-amber-700 text-sm">Human Review Required</h3>
              <div className="space-y-3">
                {flags.map((flag) => (
                  <div key={flag.flag_id} className="border border-gray-100 rounded-lg p-3 text-sm">
                    <p className="text-gray-700 mb-2">{flag.reason}</p>
                    {flag.status === 'pending' ? (
                      resolvingId === flag.flag_id ? (
                        <div className="space-y-2">
                          <textarea
                            className="w-full text-xs border border-gray-200 rounded p-2 resize-none"
                            rows={2}
                            placeholder="Reviewer notes…"
                            value={resolveNotes}
                            onChange={(e) => setResolveNotes(e.target.value)}
                          />
                          <div className="flex gap-2">
                            <button onClick={() => handleResolve(flag.flag_id, 'approved')} className="flex-1 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700">Approve</button>
                            <button onClick={() => handleResolve(flag.flag_id, 'rejected')} className="flex-1 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700">Reject</button>
                            <button onClick={() => handleResolve(flag.flag_id, 'escalated')} className="flex-1 py-1 text-xs bg-amber-500 text-white rounded hover:bg-amber-600">Escalate</button>
                          </div>
                        </div>
                      ) : (
                        <button onClick={() => setResolvingId(flag.flag_id)} className="text-xs text-blue-600 hover:underline">
                          Resolve
                        </button>
                      )
                    ) : (
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                        flag.status === 'approved' ? 'bg-green-100 text-green-700' :
                        flag.status === 'rejected' ? 'bg-red-100 text-red-700' :
                        'bg-amber-100 text-amber-700'
                      }`}>{flag.status}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right: live agent feed */}
        <div className="col-span-2">
          <div className="bg-white rounded-xl border border-gray-200 flex flex-col h-[600px]">
            <div className="px-5 py-4 border-b border-gray-100">
              <h3 className="font-semibold text-gray-800 text-sm">Agent Feed</h3>
            </div>
            <div ref={feedRef} className="flex-1 overflow-y-auto p-4 space-y-2 font-mono text-xs">
              {events.length === 0 && (
                <p className="text-gray-400 text-center mt-8">Waiting for pipeline to start…</p>
              )}
              {events.map((ev, i) => (
                <div key={i} className="flex gap-2 items-start">
                  {ev.rag_status && (
                    <span className={`mt-0.5 w-2 h-2 rounded-full flex-shrink-0 ${RAG_DOT[ev.rag_status] ?? RAG_DOT.grey}`} />
                  )}
                  <div className="flex-1">
                    <span className={`font-medium ${
                      ev.event_type === 'error' ? 'text-red-500' :
                      ev.event_type === 'report_ready' ? 'text-green-600' :
                      ev.event_type === 'hitl_flag' ? 'text-amber-600' :
                      'text-gray-700'
                    }`}>[{ev.event_type}]</span>{' '}
                    <span className="text-gray-600">{ev.message}</span>
                    {ev.score != null && (
                      <span className="ml-2 text-gray-400">score: {ev.score.toFixed(1)}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </PageLayout>
  );
}

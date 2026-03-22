'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { CheckCircle, Loader2, RefreshCw } from 'lucide-react';
import { apiClient, ApiError } from '@/lib/api';

interface WalletStatusResponse {
  stage: string;
  pct: number;
  detail: string;
}

interface PipelineStage {
  key: string;
  label: string;
}

const PIPELINE_STAGES: PipelineStage[] = [
  { key: 'indexing', label: 'Indexing' },
  { key: 'classifying', label: 'Classifying' },
  { key: 'cost_basis', label: 'Cost Basis' },
  { key: 'verifying', label: 'Verifying' },
];

// Normalize stage names from FastAPI to one of our pipeline stage keys
function normalizeStage(stage: string): string {
  const s = stage.toLowerCase();
  if (s.includes('index') || s.includes('fetch') || s.includes('sync')) return 'indexing';
  if (s.includes('classif')) return 'classifying';
  if (s.includes('acb') || s.includes('cost') || s.includes('basis')) return 'cost_basis';
  if (s.includes('verif')) return 'verifying';
  if (s === 'done' || s === 'complete') return 'done';
  return s;
}

interface SyncStatusProps {
  /** If omitted, component polls /api/jobs/active for a global status indicator */
  walletId?: number;
  /** If true, the component is shown inline on the wallet card (compact mode) */
  compact?: boolean;
  /** Called once when the pipeline transitions from active to done */
  onComplete?: () => void;
}

interface ActiveJobsResponse {
  jobs: Array<{ status: string; pipeline_stage: string; pipeline_pct: number }>;
  pipeline_stage: string;
  pipeline_pct: number;
  estimated_minutes: number | null;
}

export function SyncStatus({ walletId, compact = false, onComplete }: SyncStatusProps) {
  const [status, setStatus] = useState<WalletStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const prevDoneRef = useRef<boolean>(false);

  const fetchStatus = async () => {
    try {
      if (walletId !== undefined) {
        // Per-wallet status
        const data = await apiClient.get<WalletStatusResponse>(
          `/api/wallets/${walletId}/status`
        );
        setStatus(data);
      } else {
        // Global: use /api/jobs/active for overall pipeline stage
        const data = await apiClient.get<ActiveJobsResponse>('/api/jobs/active');
        if (data.jobs && data.jobs.length > 0) {
          const est = data.estimated_minutes;
          const timeStr = est !== null && est !== undefined
            ? est <= 1 ? '~1 min remaining'
              : est <= 60 ? `~${est} min remaining`
              : `~${Math.round(est / 60)}h remaining`
            : '';
          const jobCount = `${data.jobs.length} job${data.jobs.length === 1 ? '' : 's'} active`;
          setStatus({
            stage: data.pipeline_stage || 'indexing',
            pct: data.pipeline_pct || 0,
            detail: timeStr ? `${jobCount} — ${timeStr}` : jobCount,
          });
        } else {
          setStatus({ stage: 'done', pct: 100, detail: '' });
        }
      }
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 404)) {
        console.error('Failed to fetch sync status:', err);
      }
      // On error for global status, show nothing
      if (walletId === undefined) setStatus(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();

    // Poll every 3 seconds while a stage is active, stop when Done
    const schedule = () => {
      intervalRef.current = setInterval(async () => {
        await fetchStatus();
      }, 3000);
    };

    schedule();

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [walletId]);

  // Stop polling when done; fire onComplete callback once on transition to done
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  const handleDoneTransition = useCallback(() => {
    onCompleteRef.current?.();
  }, []);

  useEffect(() => {
    if (status && (status.stage === 'done' || status.pct >= 100)) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      // Fire onComplete only once on first transition to done state
      if (!prevDoneRef.current) {
        prevDoneRef.current = true;
        handleDoneTransition();
      }
    } else {
      prevDoneRef.current = false;
    }
  }, [status, handleDoneTransition]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-gray-400 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>Loading...</span>
      </div>
    );
  }

  if (!status) {
    // Global mode with no active jobs — show nothing
    return null;
  }

  const normalizedStage = normalizeStage(status.stage);
  const isDone = normalizedStage === 'done' || status.pct >= 100;

  // Global mode (no walletId) — always compact badge in header
  if (walletId === undefined) {
    if (isDone) return null;
    return (
      <div className="flex items-center gap-2 text-blue-400 text-sm">
        <RefreshCw className="w-4 h-4 animate-spin" />
        <span className="text-xs">{status.stage} {status.pct}%</span>
      </div>
    );
  }

  if (compact) {
    // Compact badge for wallet cards
    return (
      <div className="text-xs space-y-1">
        {isDone ? (
          <div className="flex items-center gap-1 text-green-400">
            <CheckCircle className="w-3 h-3" />
            <span>Synced</span>
          </div>
        ) : (
          <div className="flex items-center gap-1 text-blue-400">
            <RefreshCw className="w-3 h-3 animate-spin" />
            <span>{status.stage} {status.pct}%</span>
          </div>
        )}
      </div>
    );
  }

  // Full pipeline progress bar
  return (
    <div className="space-y-3">
      {/* Stage dots */}
      <div className="flex items-center justify-between relative">
        {/* Connector line behind dots */}
        <div className="absolute left-0 right-0 top-1/2 -translate-y-1/2 h-0.5 bg-gray-700 z-0" />

        {PIPELINE_STAGES.map((stage, idx) => {
          const isActive = normalizedStage === stage.key;
          const stageIdx = PIPELINE_STAGES.findIndex((s) => s.key === normalizedStage);
          const isComplete = isDone || (stageIdx > idx);

          return (
            <div key={stage.key} className="relative z-10 flex flex-col items-center gap-1">
              {/* Dot */}
              <div
                className={`w-6 h-6 rounded-full flex items-center justify-center border-2 transition-all ${
                  isComplete
                    ? 'bg-green-500 border-green-500'
                    : isActive
                    ? 'bg-blue-500 border-blue-400 animate-pulse'
                    : 'bg-gray-800 border-gray-600'
                }`}
              >
                {isComplete ? (
                  <CheckCircle className="w-3 h-3 text-white" />
                ) : isActive ? (
                  <Loader2 className="w-3 h-3 text-white animate-spin" />
                ) : (
                  <span className="w-2 h-2 rounded-full bg-gray-600" />
                )}
              </div>
              {/* Label */}
              <span
                className={`text-xs font-medium whitespace-nowrap ${
                  isComplete
                    ? 'text-green-400'
                    : isActive
                    ? 'text-blue-400'
                    : 'text-gray-500'
                }`}
              >
                {stage.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Progress percentage + detail */}
      {!isDone && (
        <div className="space-y-1">
          <div className="flex justify-between text-xs text-gray-400">
            <span>{status.stage}</span>
            <span>{status.pct}%</span>
          </div>
          {/* Progress bar */}
          <div className="h-1.5 bg-gray-700 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 transition-all duration-500"
              style={{ width: `${status.pct}%` }}
            />
          </div>
          {status.detail && (
            <p className="text-xs text-gray-500 truncate">{status.detail}</p>
          )}
        </div>
      )}

      {isDone && (
        <div className="flex items-center gap-2 text-green-400 text-sm">
          <CheckCircle className="w-4 h-4" />
          <span>Sync complete</span>
        </div>
      )}
    </div>
  );
}

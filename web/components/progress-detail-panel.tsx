'use client';

import { useEffect, useRef } from 'react';
import { X, CheckCircle, Loader2 } from 'lucide-react';

export interface JobDetail {
  id: number;
  job_type: string;
  status: string;
  progress_fetched: number | null;
  progress_total: number | null;
  error_message: string | null;
  started_at: string | null;
}

interface ProgressDetailPanelProps {
  jobs: JobDetail[];
  pipelineStage: string;
  pipelinePct: number;
  estimatedMinutes: number | null;
  onClose: () => void;
}

const PIPELINE_STAGES = [
  { label: 'Indexing', min: 0, max: 45 },
  { label: 'Classifying', min: 45, max: 65 },
  { label: 'Cost Basis', min: 65, max: 85 },
  { label: 'Verifying', min: 85, max: 100 },
];

const STAGE_COLORS: Record<string, string> = {
  Indexing: 'bg-blue-500',
  Classifying: 'bg-purple-500',
  'Cost Basis': 'bg-amber-500',
  Verifying: 'bg-green-500',
};

const JOB_TYPE_LABELS: Record<string, string> = {
  full_sync: 'Full Sync',
  incremental_sync: 'Incremental Sync',
  staking_sync: 'Staking Sync',
  lockup_sync: 'Lockup Sync',
  evm_full_sync: 'EVM Sync',
  evm_incremental: 'EVM Incremental',
  file_import: 'File Import',
  dedup_scan: 'Dedup Scan',
  classify_transactions: 'Classify',
  calculate_acb: 'Cost Basis Calc',
  verify_balances: 'Verify Balances',
  generate_reports: 'Generate Reports',
};

const STATUS_DOT_COLORS: Record<string, string> = {
  running: 'bg-green-400',
  queued: 'bg-yellow-400',
  retrying: 'bg-orange-400',
  failed: 'bg-red-400',
  completed: 'bg-gray-400',
};

function getJobLabel(jobType: string): string {
  return JOB_TYPE_LABELS[jobType] ?? jobType.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function getStatusText(job: JobDetail): string {
  if (job.progress_fetched !== null && job.progress_total !== null) {
    return `${job.progress_fetched}/${job.progress_total}`;
  }
  switch (job.status) {
    case 'running': return 'Running...';
    case 'queued': return 'Queued';
    case 'retrying': return 'Retrying...';
    case 'failed': return 'Failed';
    case 'completed': return 'Done';
    default: return job.status;
  }
}

function getStageIndex(stageName: string): number {
  const s = stageName.toLowerCase();
  if (s.includes('index') || s.includes('fetch') || s.includes('sync') || s.includes('import')) return 0;
  if (s.includes('classif')) return 1;
  if (s.includes('cost') || s.includes('basis') || s.includes('acb')) return 2;
  if (s.includes('verif')) return 3;
  return -1;
}

function getStageSpecificPct(pipelinePct: number, stageName: string): number {
  const stageIdx = getStageIndex(stageName);
  if (stageIdx < 0) return pipelinePct;
  const { min, max } = PIPELINE_STAGES[stageIdx];
  const raw = ((pipelinePct - min) / (max - min)) * 100;
  return Math.min(100, Math.max(0, Math.round(raw)));
}

export function ProgressDetailPanel({
  jobs,
  pipelineStage,
  pipelinePct,
  estimatedMinutes,
  onClose,
}: ProgressDetailPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  // Click-outside handler
  useEffect(() => {
    const handleMouseDown = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, [onClose]);

  const activeStageIdx = getStageIndex(pipelineStage);
  const stageSpecificPct = getStageSpecificPct(pipelinePct, pipelineStage);
  const stageColor = STAGE_COLORS[pipelineStage] ?? 'bg-blue-500';

  const timeStr =
    estimatedMinutes !== null && estimatedMinutes !== undefined
      ? estimatedMinutes <= 1
        ? '~1 min remaining'
        : estimatedMinutes <= 60
        ? `~${estimatedMinutes} min remaining`
        : `~${Math.round(estimatedMinutes / 60)}h remaining`
      : null;

  return (
    <div
      ref={panelRef}
      className="absolute right-0 top-full mt-2 w-80 sm:w-96 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 p-4 space-y-3"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-gray-200">Processing Details</span>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-200 transition-colors"
          aria-label="Close"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Pipeline stage stepper */}
      <div className="relative">
        {/* Connector line */}
        <div className="absolute left-3 right-3 top-3 h-0.5 bg-gray-700 z-0" />
        <div className="relative z-10 flex items-start justify-between">
          {PIPELINE_STAGES.map((stage, idx) => {
            const isComplete = activeStageIdx > idx || pipelinePct >= 100;
            const isActive = activeStageIdx === idx && pipelinePct < 100;
            return (
              <div key={stage.label} className="flex flex-col items-center gap-1 w-16">
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
                <span
                  className={`text-xs text-center whitespace-nowrap ${
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
      </div>

      {/* Overall progress */}
      <div className="space-y-1">
        <div className="flex justify-between items-center">
          <span className="text-xs text-gray-400">Overall Progress</span>
          <span className="text-xs text-gray-400">{pipelinePct}%</span>
        </div>
        <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-500 transition-all duration-500"
            style={{ width: `${pipelinePct}%` }}
          />
        </div>
        {timeStr && (
          <p className="text-xs text-gray-500">{timeStr}</p>
        )}
      </div>

      {/* Current stage progress */}
      <div className="space-y-1">
        <div className="flex justify-between items-center">
          <span className="text-xs text-gray-400">{pipelineStage}</span>
          <span className="text-xs text-gray-400">{stageSpecificPct}%</span>
        </div>
        <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ${stageColor}`}
            style={{ width: `${stageSpecificPct}%` }}
          />
        </div>
      </div>

      {/* Active jobs list */}
      {jobs.length > 0 && (
        <div className="max-h-48 overflow-y-auto space-y-0 border border-gray-700 rounded-md">
          {jobs.map((job) => {
            const hasProgress = job.progress_fetched !== null && job.progress_total !== null;
            const progressPct =
              hasProgress && job.progress_total! > 0
                ? Math.round((job.progress_fetched! / job.progress_total!) * 100)
                : 0;
            const dotColor = STATUS_DOT_COLORS[job.status] ?? 'bg-gray-400';
            return (
              <div
                key={job.id}
                className="flex items-center justify-between px-2 py-1.5 border-b border-gray-800 last:border-0"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${dotColor}`} />
                    <span className="text-xs text-gray-300 truncate">{getJobLabel(job.job_type)}</span>
                  </div>
                  {hasProgress && (
                    <div className="mt-1 h-1 w-16 bg-gray-700 rounded-full overflow-hidden ml-3.5">
                      <div
                        className="h-full bg-blue-400 transition-all duration-300"
                        style={{ width: `${progressPct}%` }}
                      />
                    </div>
                  )}
                  {job.status === 'failed' && job.error_message && (
                    <p className="text-xs text-red-400 truncate mt-0.5 ml-3.5">
                      {job.error_message}
                    </p>
                  )}
                </div>
                <span className="text-xs text-gray-400 ml-2 flex-shrink-0">
                  {getStatusText(job)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

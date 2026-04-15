'use client';

import { useState, useEffect } from 'react';
import { Loader2, Shield, Cpu, AlertTriangle, CheckCircle, XCircle } from 'lucide-react';

interface WorkerKeyStatus {
  enabled: boolean;
  last_run_at: string | null;
}

export default function BackgroundProcessingPage() {
  const [status, setStatus] = useState<WorkerKeyStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadStatus();
  }, []);

  async function loadStatus() {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch('/api/settings/worker-key', { credentials: 'include' });
      if (!r.ok) {
        setError('Failed to load background processing status.');
        return;
      }
      setStatus(await r.json());
    } catch (err) {
      setError('Failed to load background processing status.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function enableWorkerKey() {
    if (toggling) return;
    setToggling(true);
    setError(null);
    try {
      const r = await fetch('/api/settings/worker-key', {
        method: 'POST',
        credentials: 'include',
      });
      if (!r.ok) {
        const body = await r.text();
        setError(`Failed to enable background processing: ${body}`);
        return;
      }
      const data = await r.json();
      setStatus((prev) => ({ ...prev, enabled: data.enabled ?? true, last_run_at: prev?.last_run_at ?? null }));
    } catch (err) {
      setError('Failed to enable background processing.');
      console.error(err);
    } finally {
      setToggling(false);
    }
  }

  async function revokeWorkerKey() {
    if (toggling) return;
    setToggling(true);
    setError(null);
    try {
      const r = await fetch('/api/settings/worker-key', {
        method: 'DELETE',
        credentials: 'include',
      });
      if (!r.ok) {
        const body = await r.text();
        setError(`Failed to revoke background processing: ${body}`);
        return;
      }
      const data = await r.json();
      setStatus((prev) => ({ ...prev, enabled: data.enabled ?? false, last_run_at: prev?.last_run_at ?? null }));
    } catch (err) {
      setError('Failed to revoke background processing.');
      console.error(err);
    } finally {
      setToggling(false);
    }
  }

  function formatLastRun(lastRunAt: string | null): string {
    if (!lastRunAt) return 'Never';
    const d = new Date(lastRunAt);
    const diffMs = Date.now() - d.getTime();
    const diffMin = Math.floor(diffMs / 60_000);
    if (diffMin < 1) return 'Just now';
    if (diffMin < 60) return `${diffMin} minute${diffMin === 1 ? '' : 's'} ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr} hour${diffHr === 1 ? '' : 's'} ago`;
    return d.toLocaleDateString();
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Background processing</h1>
        <p className="text-gray-400 mt-1">
          Control whether Axiom can index your wallets and run reports while you are signed out.
        </p>
      </div>

      {/* Privacy explanation */}
      <div className="rounded-lg border border-gray-700 bg-gray-800 p-6 space-y-4">
        <div className="flex items-start gap-3">
          <Shield className="w-5 h-5 text-blue-400 mt-0.5 shrink-0" />
          <div className="space-y-3 text-sm text-gray-300 leading-relaxed">
            <p>
              By default, Axiom only works on your data while you&apos;re logged in. We decrypt
              your transactions in memory using a key bound to your session, so the moment
              you close the tab, no one &mdash; including us &mdash; can read your tax history.
            </p>
            <p>
              If you&apos;d rather have Axiom keep indexing wallets and running reports in the
              background while you&apos;re signed out, you can enable &quot;Background processing&quot;
              below. This stores a sealed copy of your decryption key on the server, bound
              to our worker process. We can read your data whenever our worker runs &mdash; you
              are trusting the server to hold a decryption key for you.
            </p>
          </div>
        </div>
      </div>

      {/* Toggle card */}
      <div className="rounded-lg border border-gray-700 bg-gray-800 p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-start gap-3">
            <Cpu className="w-5 h-5 text-gray-400 mt-0.5 shrink-0" />
            <div>
              <h2 className="text-white font-medium">
                Enable background processing
              </h2>
              <p className="text-xs text-amber-400 mt-0.5 flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" />
                Less private, more convenient
              </p>
            </div>
          </div>

          {loading ? (
            <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
          ) : (
            <button
              onClick={status?.enabled ? revokeWorkerKey : enableWorkerKey}
              disabled={toggling}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-800 ${
                status?.enabled
                  ? 'bg-blue-600 hover:bg-blue-500'
                  : 'bg-gray-600 hover:bg-gray-500'
              } ${toggling ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
              aria-label={
                status?.enabled
                  ? 'Disable background processing'
                  : 'Enable background processing'
              }
            >
              {toggling && (
                <Loader2 className="w-3 h-3 animate-spin text-white absolute left-1/2 -translate-x-1/2" />
              )}
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  status?.enabled ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          )}
        </div>

        {/* Status block */}
        {!loading && status !== null && (
          <div className="border-t border-gray-700 pt-4">
            {status.enabled ? (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                  <CheckCircle className="w-4 h-4 text-green-400" />
                  <span className="text-green-400 font-medium">Worker active</span>
                  {status.last_run_at && (
                    <span className="text-gray-400">
                      &mdash; last run {formatLastRun(status.last_run_at)}
                    </span>
                  )}
                  {!status.last_run_at && (
                    <span className="text-gray-400">&mdash; not yet run</span>
                  )}
                </div>
                <button
                  onClick={revokeWorkerKey}
                  disabled={toggling}
                  className="text-xs text-red-400 hover:text-red-300 transition-colors disabled:opacity-50 border border-red-800 hover:border-red-600 rounded px-2 py-1"
                >
                  Revoke
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm">
                <XCircle className="w-4 h-4 text-gray-500" />
                <span className="text-gray-400">
                  Background processing is disabled. Your data is only processed while you are logged in.
                </span>
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="border-t border-gray-700 pt-4">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}
      </div>

      {/* Audit trail notice */}
      <p className="text-xs text-gray-500">
        Every change to this setting is recorded in your audit log. You can view your audit history
        in the Axiom dashboard.
      </p>
    </div>
  );
}

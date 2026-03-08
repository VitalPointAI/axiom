'use client';

import { useState, useEffect, useCallback } from 'react';
import { 
  RefreshCw, 
  CheckCircle, 
  AlertCircle, 
  Clock, 
  Loader2, 
  Play,
  AlertTriangle,
  Database,
  Coins,
  Wallet,
  TrendingUp,
  Lock,
  Droplets
} from 'lucide-react';

interface IndexerData {
  indexer_name: string;
  display_name: string;
  description: string;
  last_run_at: string | null;
  last_success_at: string | null;
  status: 'unknown' | 'running' | 'success' | 'error';
  last_error: string | null;
  records_processed: number;
  run_duration_seconds: number | null;
  cron_schedule: string | null;
  is_enabled: boolean;
  health_status: 'never' | 'stale' | 'error' | 'running' | 'healthy';
  seconds_since_success: number | null;
}

interface WalletStats {
  [blockchain: string]: {
    total: number;
    synced: number;
  };
}

const indexerIcons: Record<string, typeof Database> = {
  'near_indexer': Database,
  'ft_indexer': Coins,
  'evm_indexer': Wallet,
  'staking_indexer': TrendingUp,
  'burrow_tracker': Droplets,
  'mpdao_tracker': Lock,
  'sweat_jars': Droplets,
  'price_indexer': TrendingUp,
};

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${mins}m`;
}

function formatTimeSince(seconds: number | null): string {
  if (seconds === null) return 'Never';
  if (seconds < 60) return 'Just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
  return `${Math.floor(seconds / 86400)} days ago`;
}

function getHealthColor(health: string): string {
  switch (health) {
    case 'healthy': return 'text-green-400';
    case 'running': return 'text-blue-400';
    case 'stale': return 'text-amber-400';
    case 'error': return 'text-red-400';
    default: return 'text-gray-400';
  }
}

function getHealthBg(health: string): string {
  switch (health) {
    case 'healthy': return 'bg-green-500/10 border-green-500/30';
    case 'running': return 'bg-blue-500/10 border-blue-500/30';
    case 'stale': return 'bg-amber-500/10 border-amber-500/30';
    case 'error': return 'bg-red-500/10 border-red-500/30';
    default: return 'bg-gray-500/10 border-gray-500/30';
  }
}

function HealthIcon({ health }: { health: string }) {
  switch (health) {
    case 'healthy':
      return <CheckCircle className="w-5 h-5 text-green-400" />;
    case 'running':
      return <RefreshCw className="w-5 h-5 text-blue-400 animate-spin" />;
    case 'stale':
      return <AlertTriangle className="w-5 h-5 text-amber-400" />;
    case 'error':
      return <AlertCircle className="w-5 h-5 text-red-400" />;
    default:
      return <Clock className="w-5 h-5 text-gray-400" />;
  }
}

export function IndexerStatus() {
  const [indexers, setIndexers] = useState<IndexerData[]>([]);
  const [walletStats, setWalletStats] = useState<WalletStats>({});
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/indexers/status');
      if (res.ok) {
        const data = await res.json();
        setIndexers(data.indexers);
        setWalletStats(data.walletStats || {});
        setError(null);
      } else {
        setError('Failed to fetch indexer status');
      }
    } catch (err) {
      setError('Failed to fetch indexer status');
      console.error('Failed to fetch indexer status:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const runIndexer = async (indexerName: string) => {
    setRunning(indexerName);
    try {
      const res = await fetch('/api/indexers/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ indexer_name: indexerName })
      });
      
      if (res.ok) {
        // Wait a moment for the indexer to start
        await new Promise(r => setTimeout(r, 2000));
        await fetchStatus();
      } else {
        const data = await res.json();
        alert(`Failed to start indexer: ${data.error || 'Unknown error'}`);
      }
    } catch (err) {
      console.error('Failed to run indexer:', err);
      alert('Failed to start indexer');
    } finally {
      setRunning(null);
    }
  };

  // Calculate overall health
  const healthyCounts = {
    healthy: indexers.filter(i => i.health_status === 'healthy').length,
    running: indexers.filter(i => i.health_status === 'running').length,
    stale: indexers.filter(i => i.health_status === 'stale').length,
    error: indexers.filter(i => i.health_status === 'error').length,
    never: indexers.filter(i => i.health_status === 'never').length,
  };

  const overallHealth = healthyCounts.error > 0 ? 'error' :
    healthyCounts.stale > 0 ? 'stale' :
    healthyCounts.running > 0 ? 'running' : 'healthy';

  if (loading) {
    return (
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
        <div className="flex items-center gap-3 text-gray-400">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Loading indexer status...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-gray-900 rounded-lg border border-red-800 p-6">
        <div className="flex items-center gap-3 text-red-400">
          <AlertCircle className="w-5 h-5" />
          <span>{error}</span>
          <button
            onClick={fetchStatus}
            className="ml-auto text-sm text-blue-400 hover:text-blue-300"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Database className="w-5 h-5 text-gray-400" />
          <h2 className="text-lg font-semibold text-white">Indexer Status</h2>
          <div className={`px-2 py-0.5 rounded text-xs font-medium ${getHealthBg(overallHealth)} ${getHealthColor(overallHealth)}`}>
            {healthyCounts.healthy}/{indexers.length} Healthy
          </div>
        </div>
        <button
          onClick={fetchStatus}
          className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
          title="Refresh Status"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Wallet Coverage Summary */}
      {Object.keys(walletStats).length > 0 && (
        <div className="px-6 py-3 border-b border-gray-800 bg-gray-800/50">
          <h3 className="text-xs text-gray-400 uppercase tracking-wide mb-2">Wallet Coverage</h3>
          <div className="flex flex-wrap gap-4">
            {Object.entries(walletStats).map(([chain, stats]) => (
              <div key={chain} className="flex items-center gap-2 text-sm">
                <span className="text-gray-400 capitalize">{chain}:</span>
                <span className={stats.synced === stats.total ? 'text-green-400' : 'text-amber-400'}>
                  {stats.synced}/{stats.total}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Indexer List */}
      <div className="divide-y divide-gray-800">
        {indexers.map((indexer) => {
          const Icon = indexerIcons[indexer.indexer_name] || Database;
          const isRunningThisOne = running === indexer.indexer_name;
          
          return (
            <div
              key={indexer.indexer_name}
              className={`px-6 py-4 hover:bg-gray-800/50 transition-colors ${getHealthBg(indexer.health_status)}`}
            >
              <div className="flex items-center gap-4">
                {/* Icon & Name */}
                <div className="flex items-center gap-3 min-w-[200px]">
                  <Icon className={`w-5 h-5 ${getHealthColor(indexer.health_status)}`} />
                  <div>
                    <div className="font-medium text-white">{indexer.display_name}</div>
                    <div className="text-xs text-gray-400">{indexer.description}</div>
                  </div>
                </div>

                {/* Status */}
                <div className="flex items-center gap-2 min-w-[120px]">
                  <HealthIcon health={indexer.health_status} />
                  <span className={`text-sm capitalize ${getHealthColor(indexer.health_status)}`}>
                    {indexer.health_status === 'never' ? 'Never Run' : indexer.health_status}
                  </span>
                </div>

                {/* Last Run */}
                <div className="min-w-[120px] text-sm">
                  <div className="text-gray-400">Last Success</div>
                  <div className="text-white">
                    {formatTimeSince(indexer.seconds_since_success)}
                  </div>
                </div>

                {/* Records & Duration */}
                <div className="min-w-[100px] text-sm">
                  <div className="text-gray-400">Records</div>
                  <div className="text-white">
                    {indexer.records_processed > 0 
                      ? indexer.records_processed.toLocaleString() 
                      : '-'}
                  </div>
                </div>

                <div className="min-w-[80px] text-sm">
                  <div className="text-gray-400">Duration</div>
                  <div className="text-white">
                    {indexer.run_duration_seconds 
                      ? formatDuration(indexer.run_duration_seconds) 
                      : '-'}
                  </div>
                </div>

                {/* Schedule */}
                <div className="min-w-[100px] text-sm">
                  <div className="text-gray-400">Schedule</div>
                  <div className="text-white font-mono text-xs">
                    {indexer.cron_schedule || 'Manual'}
                  </div>
                </div>

                {/* Actions */}
                <div className="ml-auto">
                  <button
                    onClick={() => runIndexer(indexer.indexer_name)}
                    disabled={isRunningThisOne || indexer.health_status === 'running'}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-400 text-white rounded transition-colors"
                  >
                    {isRunningThisOne || indexer.health_status === 'running' ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Running
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4" />
                        Run
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Error Message */}
              {indexer.last_error && (
                <div className="mt-2 px-8 py-2 bg-red-900/30 border border-red-800 rounded text-sm text-red-300">
                  <span className="font-medium">Error:</span> {indexer.last_error}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="px-6 py-3 border-t border-gray-800 bg-gray-800/30">
        <div className="flex items-center gap-6 text-xs text-gray-400">
          <div className="flex items-center gap-1.5">
            <CheckCircle className="w-3.5 h-3.5 text-green-400" />
            <span>Healthy (&lt;24h)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            <span>Stale (&gt;24h)</span>
          </div>
          <div className="flex items-center gap-1.5">
            <AlertCircle className="w-3.5 h-3.5 text-red-400" />
            <span>Error</span>
          </div>
          <div className="flex items-center gap-1.5">
            <RefreshCw className="w-3.5 h-3.5 text-blue-400" />
            <span>Running</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5 text-gray-400" />
            <span>Never Run</span>
          </div>
        </div>
      </div>
    </div>
  );
}

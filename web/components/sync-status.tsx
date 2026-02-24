'use client';

import { useState, useEffect } from 'react';
import { RefreshCw, CheckCircle, AlertCircle, Clock, Loader2 } from 'lucide-react';

interface SyncStatus {
  status: 'idle' | 'syncing' | 'complete' | 'error';
  progress: number;
  wallets: {
    total: number;
    synced: number;
    inProgress: number;
    error: number;
    pending: number;
  };
  transactions: {
    total: number;
    blockRange: { min: number; max: number } | null;
    dateRange: { oldest: string; newest: string } | null;
  };
  indexer: {
    position: number;
    status: string;
    lastUpdated: string;
  } | null;
  lastChecked: string;
}

export function SyncStatus() {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const fetchStatus = async () => {
    try {
      const res = await fetch('/api/sync/status');
      if (res.ok) {
        const data = await res.json();
        setStatus(data);
      }
    } catch (error) {
      console.error('Failed to fetch sync status:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    // Poll every 10 seconds if syncing, otherwise every 30 seconds
    const interval = setInterval(() => {
      fetchStatus();
    }, status?.status === 'syncing' ? 10000 : 30000);
    
    return () => clearInterval(interval);
  }, [status?.status]);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-gray-400 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>Loading sync status...</span>
      </div>
    );
  }

  if (!status) {
    return null;
  }

  const getStatusIcon = () => {
    switch (status.status) {
      case 'syncing':
        return <RefreshCw className="w-4 h-4 animate-spin text-blue-400" />;
      case 'complete':
        return <CheckCircle className="w-4 h-4 text-green-400" />;
      case 'error':
        return <AlertCircle className="w-4 h-4 text-red-400" />;
      default:
        return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  const getStatusText = () => {
    switch (status.status) {
      case 'syncing':
        return 'Syncing...';
      case 'complete':
        return 'Synced';
      case 'error':
        return 'Sync Error';
      default:
        return 'Idle';
    }
  };

  const getStatusColor = () => {
    switch (status.status) {
      case 'syncing':
        return 'bg-blue-500/20 border-blue-500/50 text-blue-400';
      case 'complete':
        return 'bg-green-500/20 border-green-500/50 text-green-400';
      case 'error':
        return 'bg-red-500/20 border-red-500/50 text-red-400';
      default:
        return 'bg-gray-500/20 border-gray-500/50 text-gray-400';
    }
  };

  const formatNumber = (n: number) => n?.toLocaleString() || '0';
  const formatBlock = (n: number) => n ? `#${n.toLocaleString()}` : '-';

  return (
    <div className="relative">
      {/* Compact Status Badge */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border text-sm transition-colors ${getStatusColor()} hover:opacity-80`}
      >
        {getStatusIcon()}
        <span>{getStatusText()}</span>
        {status.status === 'syncing' && (
          <span className="text-xs opacity-75">
            {status.progress}%
          </span>
        )}
      </button>

      {/* Expanded Details Panel */}
      {expanded && (
        <div className="absolute right-0 top-full mt-2 w-80 bg-gray-800 border border-gray-700 rounded-lg shadow-xl p-4 z-50">
          <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
              <h3 className="font-medium text-white">Sync Status</h3>
              <button
                onClick={fetchStatus}
                className="text-gray-400 hover:text-white"
                title="Refresh"
              >
                <RefreshCw className="w-4 h-4" />
              </button>
            </div>

            {/* Progress Bar */}
            {status.status === 'syncing' && (
              <div>
                <div className="flex justify-between text-xs text-gray-400 mb-1">
                  <span>Progress</span>
                  <span>{status.progress}%</span>
                </div>
                <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-blue-500 transition-all duration-500"
                    style={{ width: `${status.progress}%` }}
                  />
                </div>
              </div>
            )}

            {/* Wallet Stats */}
            <div>
              <h4 className="text-xs text-gray-400 uppercase tracking-wide mb-2">Wallets</h4>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">Total</span>
                  <span className="text-white">{formatNumber(status.wallets.total)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-green-400">Synced</span>
                  <span className="text-white">{formatNumber(status.wallets.synced)}</span>
                </div>
                {status.wallets.inProgress > 0 && (
                  <div className="flex justify-between">
                    <span className="text-blue-400">In Progress</span>
                    <span className="text-white">{formatNumber(status.wallets.inProgress)}</span>
                  </div>
                )}
                {status.wallets.error > 0 && (
                  <div className="flex justify-between">
                    <span className="text-red-400">Error</span>
                    <span className="text-white">{formatNumber(status.wallets.error)}</span>
                  </div>
                )}
                {status.wallets.pending > 0 && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">Pending</span>
                    <span className="text-white">{formatNumber(status.wallets.pending)}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Transaction Stats */}
            <div>
              <h4 className="text-xs text-gray-400 uppercase tracking-wide mb-2">Transactions</h4>
              <div className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-400">Total Indexed</span>
                  <span className="text-white font-medium">{formatNumber(status.transactions.total)}</span>
                </div>
                {status.transactions.blockRange && (
                  <div className="flex justify-between">
                    <span className="text-gray-400">Block Range</span>
                    <span className="text-white text-xs">
                      {formatBlock(status.transactions.blockRange.min)} → {formatBlock(status.transactions.blockRange.max)}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Indexer Status */}
            {status.indexer && (
              <div>
                <h4 className="text-xs text-gray-400 uppercase tracking-wide mb-2">Indexer</h4>
                <div className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Status</span>
                    <span className={`capitalize ${
                      status.indexer.status === 'scanning' ? 'text-blue-400' :
                      status.indexer.status === 'done' ? 'text-green-400' : 'text-gray-400'
                    }`}>
                      {status.indexer.status}
                    </span>
                  </div>
                  {status.indexer.position && (
                    <div className="flex justify-between">
                      <span className="text-gray-400">Position</span>
                      <span className="text-white">{formatBlock(status.indexer.position)}</span>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Last Updated */}
            <div className="text-xs text-gray-500 pt-2 border-t border-gray-700">
              Last checked: {new Date(status.lastChecked).toLocaleTimeString()}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

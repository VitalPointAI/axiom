'use client';

import { useEffect, useState } from 'react';
import { CheckCircle, XCircle, AlertTriangle, RefreshCw, Database, HardDrive } from 'lucide-react';

interface WalletVerification {
  account: string;
  label: string | null;
  onChain: number;
  computed: number;
  storageCost: number;
  hasContract: boolean;
  diff: number;
  match: boolean;
  details: any;
}

interface VerificationData {
  wallets: WalletVerification[];
  totals?: { 
    onChain: number; 
    computed: number; 
    storage: number;
    diff: number;
  };
  summary: { total: number; matching: number; mismatched: number };
  note?: string;
  error?: string;
}

export function WalletVerification() {
  const [data, setData] = useState<VerificationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch('/api/wallets/verify');
      if (!res.ok) {
        if (res.status === 401) {
          throw new Error('Please sign in to view wallet verification');
        }
        throw new Error('Failed to fetch');
      }
      const json = await res.json();
      // Validate response has expected structure
      if (json.error) {
        throw new Error(json.error);
      }
      setData(json);
    } catch (err: any) {
      setError(err.message || 'Failed to verify wallets');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-sm border p-6 animate-pulse">
        <div className="h-6 bg-slate-200 rounded w-1/3 mb-4"></div>
        <div className="h-32 bg-slate-200 rounded"></div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <p className="text-red-500">{error || 'No data'}</p>
        <button onClick={fetchData} className="mt-2 text-sm text-blue-500 hover:underline">Retry</button>
      </div>
    );
  }

  // Handle case where wallets array is empty or totals is missing
  if (!data.wallets || data.wallets.length === 0 || !data.totals) {
    return (
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <h2 className="text-lg font-semibold text-slate-700 mb-2">Wallet Verification</h2>
        <p className="text-slate-500">No wallets to verify. Add some wallets first.</p>
      </div>
    );
  }

  const displayWallets = showAll ? data.wallets : data.wallets.slice(0, 15);
  const totals = data.totals;

  return (
    <div className="bg-white rounded-lg shadow-sm border p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-700">Wallet Verification</h2>
          <p className="text-sm text-slate-500">On-chain vs tracked balances</p>
        </div>
        <button onClick={fetchData} className="p-2 hover:bg-slate-100 rounded-lg transition" title="Refresh">
          <RefreshCw className="w-4 h-4 text-slate-400" />
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <div className="bg-blue-50 rounded-lg p-3 text-center">
          <p className="text-xl font-bold text-blue-700">{totals.onChain.toLocaleString(undefined, {maximumFractionDigits: 0})}</p>
          <p className="text-xs text-slate-600">On-Chain Ⓝ</p>
        </div>
        <div className="bg-purple-50 rounded-lg p-3 text-center">
          <p className="text-xl font-bold text-purple-700">{totals.computed.toLocaleString(undefined, {maximumFractionDigits: 0})}</p>
          <p className="text-xs text-slate-600">Tracked Ⓝ</p>
        </div>
        <div className="bg-amber-50 rounded-lg p-3 text-center">
          <p className="text-xl font-bold text-amber-700">{totals.storage.toLocaleString(undefined, {maximumFractionDigits: 1})}</p>
          <p className="text-xs text-slate-600">Storage Ⓝ</p>
        </div>
        <div className={"rounded-lg p-3 text-center " + (Math.abs(totals.diff) > 50 ? "bg-red-50" : "bg-green-50")}>
          <p className={"text-xl font-bold " + (Math.abs(totals.diff) > 50 ? "text-red-700" : "text-green-700")}>
            {totals.diff > 0 ? '+' : ''}{totals.diff.toLocaleString(undefined, {maximumFractionDigits: 0})}
          </p>
          <p className="text-xs text-slate-600">Diff Ⓝ</p>
        </div>
      </div>

      {/* Status Bar */}
      <div className="flex items-center gap-4 mb-4 p-3 bg-slate-50 rounded-lg">
        <div className="flex items-center gap-1">
          <CheckCircle className="w-4 h-4 text-green-500" />
          <span className="text-sm">{data.summary.matching} match</span>
        </div>
        <div className="flex items-center gap-1">
          <XCircle className="w-4 h-4 text-red-500" />
          <span className="text-sm">{data.summary.mismatched} mismatched</span>
        </div>
        {Math.abs(totals.diff) > 50 && (
          <div className="flex items-center gap-1 ml-auto">
            <AlertTriangle className="w-4 h-4 text-amber-500" />
            <span className="text-sm text-amber-600">
              {totals.diff > 0 ? 'Over-counting (missing outflows)' : 'Under-counting (missing inflows)'}
            </span>
          </div>
        )}
      </div>

      {/* Wallet List */}
      <div className="max-h-80 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500 border-b sticky top-0 bg-white">
            <tr>
              <th className="pb-2">Wallet</th>
              <th className="pb-2 text-right">On-Chain</th>
              <th className="pb-2 text-right">Tracked</th>
              <th className="pb-2 text-right" title="Storage locked for account/contract data">
                <span className="flex items-center justify-end gap-1">
                  <HardDrive className="w-3 h-3" />
                  Storage
                </span>
              </th>
              <th className="pb-2 text-right" title="Tracked - OnChain">Diff</th>
              <th className="pb-2 text-center">Status</th>
            </tr>
          </thead>
          <tbody>
            {displayWallets.map((w, i) => (
              <tr key={i} className="border-b border-slate-100 hover:bg-slate-50">
                <td className="py-2 font-mono text-xs">
                  <div className="flex items-center gap-1">
                    {w.hasContract && (
                      <span title="Contract account">
                        <Database className="w-3 h-3 text-blue-500" />
                      </span>
                    )}
                    <span title={w.account}>
                      {w.account.length > 20 ? w.account.slice(0, 10) + '...' + w.account.slice(-8) : w.account}
                    </span>
                  </div>
                </td>
                <td className="py-2 text-right">{(w.onChain ?? 0).toLocaleString(undefined, {maximumFractionDigits: 2})}</td>
                <td className="py-2 text-right">{(w.computed ?? 0).toLocaleString(undefined, {maximumFractionDigits: 2})}</td>
                <td className="py-2 text-right text-amber-600">
                  {(w.storageCost ?? 0) > 0.01 ? (w.storageCost ?? 0).toFixed(2) : '-'}
                </td>
                <td className={"py-2 text-right font-medium " + (
                  Math.abs(w.diff ?? 0) > 5 ? "text-red-600" : 
                  Math.abs(w.diff ?? 0) > 1 ? "text-amber-600" : "text-slate-500"
                )}>
                  {(w.diff ?? 0) > 0 ? '+' : ''}{(w.diff ?? 0).toFixed(2)}
                </td>
                <td className="py-2 text-center">
                  {w.match ? (
                    <CheckCircle className="w-4 h-4 text-green-500 inline" />
                  ) : (
                    <XCircle className="w-4 h-4 text-red-500 inline" />
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Show more/less */}
      {data.wallets.length > 15 && (
        <button 
          onClick={() => setShowAll(!showAll)}
          className="mt-3 text-sm text-blue-500 hover:underline"
        >
          {showAll ? `Show less` : `Show all ${data.wallets.length} wallets`}
        </button>
      )}

      {data.note && <p className="text-xs text-slate-400 mt-3">{data.note}</p>}
    </div>
  );
}

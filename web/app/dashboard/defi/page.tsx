'use client';

import { useState, useEffect } from 'react';
import { Coins, TrendingUp, RefreshCw, AlertTriangle, Banknote, PiggyBank, Shield, CreditCard } from 'lucide-react';

interface Position {
  protocol: string;
  token: string;
  contract: string;
  amount: number;
  price: number;
  valueUsd: number;
  wallet: string;
}

interface DefiPositions {
  positions: {
    supplied: Position[];
    collateral: Position[];
    borrowed: Position[];
    staking: Position[];
    farming: Position[];
    liquidity: Position[];
  };
  totals: {
    supplied: number;
    collateral: number;
    borrowed: number;
    staking: number;
    farming: number;
    liquidity: number;
    netValue: number;
  };
}

interface DefiSummary {
  byCategory: Array<{
    year: string;
    tax_category: string;
    protocol: string;
    count: number;
    total_usd: number;
  }>;
  protocols: Array<{
    protocol: string;
    count: number;
  }>;
  needsReview: number;
}

export default function DefiPage() {
  const [positions, setPositions] = useState<DefiPositions | null>(null);
  const [summary, setSummary] = useState<DefiSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [posRes, sumRes] = await Promise.all([
        fetch('/api/defi/positions'),
        fetch('/api/defi/summary')
      ]);
      const [posData, sumData] = await Promise.all([posRes.json(), sumRes.json()]);
      setPositions(posData);
      setSummary(sumData);
    } catch (err) {
      console.error('Failed to fetch DeFi data:', err);
    } finally {
      setLoading(false);
    }
  };

  const syncBurrow = async () => {
    setSyncing(true);
    try {
      await fetch('/api/defi/sync', { method: 'POST' });
      await fetchData();
    } catch (err) {
      console.error('Sync failed:', err);
    } finally {
      setSyncing(false);
    }
  };

  const formatUsd = (val: number) => {
    if (val >= 1000) return `$${(val/1000).toFixed(1)}K`;
    return `$${val.toFixed(2)}`;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-slate-400" />
      </div>
    );
  }

  const totals = positions?.totals || { supplied: 0, collateral: 0, borrowed: 0, netValue: 0 };
  const pos = positions?.positions || { supplied: [], collateral: [], borrowed: [], staking: [], farming: [], liquidity: [] };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">DeFi Positions</h1>
          <p className="text-slate-500 dark:text-slate-400">
            Your lending, borrowing, and yield positions
          </p>
        </div>
        <button
          onClick={syncBurrow}
          disabled={syncing}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${syncing ? 'animate-spin' : ''}`} />
          Sync Positions
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-2 text-green-600 mb-2">
            <PiggyBank className="w-5 h-5" />
            <span className="text-sm font-medium">Supplied</span>
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white">
            {formatUsd(totals.supplied)}
          </div>
        </div>
        
        <div className="bg-white dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-2 text-blue-600 mb-2">
            <Shield className="w-5 h-5" />
            <span className="text-sm font-medium">Collateral</span>
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white">
            {formatUsd(totals.collateral)}
          </div>
        </div>
        
        <div className="bg-white dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-2 text-red-600 mb-2">
            <CreditCard className="w-5 h-5" />
            <span className="text-sm font-medium">Borrowed</span>
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white">
            {formatUsd(totals.borrowed)}
          </div>
        </div>
        
        <div className="bg-white dark:bg-slate-800 rounded-xl p-4 border border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-2 text-purple-600 mb-2">
            <TrendingUp className="w-5 h-5" />
            <span className="text-sm font-medium">Net Value</span>
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white">
            {formatUsd(totals.netValue)}
          </div>
        </div>
      </div>

      {/* Current Positions */}
      <div className="grid md:grid-cols-2 gap-6">
        {/* Supplied + Collateral */}
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700">
          <div className="p-4 border-b border-slate-200 dark:border-slate-700">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2">
              <PiggyBank className="w-5 h-5 text-green-600" />
              Supplied & Collateral
            </h2>
          </div>
          <div className="divide-y divide-slate-100 dark:divide-slate-700">
            {[...pos.supplied, ...pos.collateral].map((p, i) => (
              <div key={i} className="p-4 flex justify-between items-center">
                <div>
                  <div className="font-medium text-slate-900 dark:text-white">{p.token}</div>
                  <div className="text-sm text-slate-500">
                    {p.amount.toFixed(4)} @ ${p.price.toFixed(4)}
                  </div>
                  <div className="text-xs text-slate-400">{p.protocol}</div>
                </div>
                <div className="text-right">
                  <div className="font-semibold text-green-600">${p.valueUsd.toFixed(2)}</div>
                </div>
              </div>
            ))}
            {pos.supplied.length === 0 && pos.collateral.length === 0 && (
              <div className="p-4 text-slate-500 text-center">No positions</div>
            )}
          </div>
        </div>

        {/* Borrowed */}
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700">
          <div className="p-4 border-b border-slate-200 dark:border-slate-700">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2">
              <CreditCard className="w-5 h-5 text-red-600" />
              Borrowed
            </h2>
          </div>
          <div className="divide-y divide-slate-100 dark:divide-slate-700">
            {pos.borrowed.map((p, i) => (
              <div key={i} className="p-4 flex justify-between items-center">
                <div>
                  <div className="font-medium text-slate-900 dark:text-white">{p.token}</div>
                  <div className="text-sm text-slate-500">
                    {p.amount.toFixed(4)} @ ${p.price.toFixed(4)}
                  </div>
                  <div className="text-xs text-slate-400">{p.protocol}</div>
                </div>
                <div className="text-right">
                  <div className="font-semibold text-red-600">-${p.valueUsd.toFixed(2)}</div>
                </div>
              </div>
            ))}
            {pos.borrowed.length === 0 && (
              <div className="p-4 text-slate-500 text-center">No outstanding loans</div>
            )}
          </div>
        </div>
      </div>

      {/* Protocol Summary */}
      {summary && summary.protocols && summary.protocols.length > 0 && (
        <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700">
          <div className="p-4 border-b border-slate-200 dark:border-slate-700">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Protocol Activity</h2>
          </div>
          <div className="p-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {summary.protocols.slice(0, 8).map((p, i) => (
                <div key={i} className="text-center p-3 bg-slate-50 dark:bg-slate-700/50 rounded-lg">
                  <div className="font-medium text-slate-900 dark:text-white capitalize">
                    {p.protocol.replace(/_/g, ' ')}
                  </div>
                  <div className="text-2xl font-bold text-blue-600">{p.count}</div>
                  <div className="text-xs text-slate-500">transactions</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Warnings */}
      {summary && summary.needsReview > 0 && (
        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-xl p-4">
          <div className="flex items-center gap-2 text-amber-800 dark:text-amber-200">
            <AlertTriangle className="w-5 h-5" />
            <span>{summary.needsReview} DeFi transactions need review</span>
          </div>
        </div>
      )}
    </div>
  );
}

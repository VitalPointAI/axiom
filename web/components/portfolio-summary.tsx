'use client';

import { useEffect, useState } from 'react';
import { TrendingUp, TrendingDown, Wallet, Coins, RefreshCw } from 'lucide-react';

interface PortfolioData {
  totalValue: number;
  change24h: number;
  walletCount: number;
  assetCount: number;
  holdings: Array<{
    asset: string;
    amount: number;
    chain: string;
    price: number;
    value: number;
  }>;
  staking: Array<{
    validator: string;
    staked: number;
    rewards: number;
    value: number;
  }>;
}

export function PortfolioSummary() {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/portfolio');
      if (!res.ok) throw new Error('Failed to fetch');
      const json = await res.json();
      setData(json);
      setError(null);
    } catch (err) {
      setError('Failed to load portfolio data');
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
        <div className="h-8 bg-slate-200 rounded w-1/3 mb-4"></div>
        <div className="h-12 bg-slate-200 rounded w-1/2 mb-2"></div>
        <div className="h-4 bg-slate-200 rounded w-1/4"></div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <p className="text-red-500">{error || 'No data available'}</p>
        <button 
          onClick={fetchData}
          className="mt-2 text-sm text-blue-500 hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  const isPositive = data.change24h >= 0;

  return (
    <div className="bg-white rounded-lg shadow-sm border p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-700">Portfolio Value</h2>
        <button 
          onClick={fetchData}
          className="p-2 hover:bg-slate-100 rounded-lg transition"
          title="Refresh"
        >
          <RefreshCw className="w-4 h-4 text-slate-400" />
        </button>
      </div>

      <div className="mb-4">
        <p className="text-4xl font-bold text-slate-900">
          ${data.totalValue.toLocaleString(undefined, { 
            minimumFractionDigits: 2,
            maximumFractionDigits: 2 
          })}
        </p>
        <div className={`flex items-center gap-1 mt-1 ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
          {isPositive ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
          <span className="text-sm font-medium">
            {isPositive ? '+' : ''}{data.change24h.toFixed(2)}% (24h)
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 pt-4 border-t">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-blue-50 rounded-lg">
            <Wallet className="w-4 h-4 text-blue-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900">{data.walletCount}</p>
            <p className="text-xs text-slate-500">Wallets</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="p-2 bg-purple-50 rounded-lg">
            <Coins className="w-4 h-4 text-purple-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900">{data.assetCount}</p>
            <p className="text-xs text-slate-500">Assets</p>
          </div>
        </div>
      </div>
    </div>
  );
}

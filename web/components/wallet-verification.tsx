'use client';

import { useEffect, useState } from 'react';
import { CheckCircle, RefreshCw, Database, Wallet, Coins, ExternalLink } from 'lucide-react';

interface WalletData {
  account: string;
  label: string | null;
  walletId: number;
  chain: string;
  chainName: string;
  symbol: string;
  liquidBalance: number;
  stakedBalance: number;
  totalBalance: number;
  txCount: number;
  hasStaking: boolean;
  stakingNote?: string;
}

interface ExchangeAccount {
  account: string;
  label: string | null;
  balances: Record<string, number>;
  totalCad: number;
}

interface VerificationData {
  wallets: WalletData[];
  exchangeAccounts?: ExchangeAccount[];
  summary: { 
    total: number; 
    nearWallets: number; 
    evmWallets: number;
    exchangeAccounts: number;
  };
  totals?: {
    nearLiquid: number;
    nearStaked: number;
    nearTotal: number;
  };
  note?: string;
  error?: string;
}

const CHAIN_COLORS: Record<string, string> = {
  'NEAR': 'bg-emerald-100 text-emerald-700',
  'ethereum': 'bg-blue-100 text-blue-700',
  'polygon': 'bg-purple-100 text-purple-700',
  'optimism': 'bg-red-100 text-red-700',
};

const EXPLORER_URLS: Record<string, string> = {
  'NEAR': 'https://nearblocks.io/address/',
  'ethereum': 'https://etherscan.io/address/',
  'polygon': 'https://polygonscan.com/address/',
  'optimism': 'https://optimistic.etherscan.io/address/',
};

export function WalletVerification() {
  const [data, setData] = useState<VerificationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [chainFilter, setChainFilter] = useState<string>('');

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams();
      if (chainFilter) params.set('chain', chainFilter);
      
      const res = await fetch(`/api/wallets/verify?${params}`);
      if (!res.ok) {
        if (res.status === 401) {
          throw new Error('Please sign in to view wallet balances');
        }
        throw new Error('Failed to fetch');
      }
      const json = await res.json();
      if (json.error) {
        throw new Error(json.error);
      }
      setData(json);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch wallet balances');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [chainFilter]);

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center gap-3">
          <RefreshCw className="w-5 h-5 animate-spin text-slate-400" />
          <span className="text-slate-500">Loading wallet balances...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <div className="text-red-600">{error}</div>
        <button 
          onClick={fetchData}
          className="mt-3 text-sm text-blue-500 hover:underline flex items-center gap-1"
        >
          <RefreshCw className="w-4 h-4" /> Retry
        </button>
      </div>
    );
  }

  if (!data || data.wallets.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <p className="text-slate-500">No wallets to display. Add some wallets first.</p>
      </div>
    );
  }

  const displayWallets = showAll ? data.wallets : data.wallets.slice(0, 15);

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Wallet className="w-6 h-6 text-emerald-600" />
          <h2 className="text-lg font-semibold text-slate-800">Wallet Balances</h2>
          <span className="text-sm text-slate-500">
            ({data.summary.total} wallets)
          </span>
        </div>
        <button 
          onClick={fetchData}
          className="text-sm text-blue-500 hover:underline flex items-center gap-1"
          disabled={loading}
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* NEAR Totals */}
      {data.totals && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-emerald-50 rounded-lg p-4">
            <div className="text-sm text-emerald-600 mb-1">Liquid NEAR</div>
            <div className="text-xl font-bold text-emerald-800">
              {data.totals.nearLiquid.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
            </div>
          </div>
          <div className="bg-blue-50 rounded-lg p-4">
            <div className="text-sm text-blue-600 mb-1">Staked NEAR</div>
            <div className="text-xl font-bold text-blue-800">
              {data.totals.nearStaked.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
            </div>
          </div>
          <div className="bg-slate-100 rounded-lg p-4">
            <div className="text-sm text-slate-600 mb-1">Total NEAR</div>
            <div className="text-xl font-bold text-slate-800">
              {data.totals.nearTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
            </div>
          </div>
        </div>
      )}

      {/* Wallets Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="pb-3 font-medium">Wallet</th>
              <th className="pb-3 font-medium">Chain</th>
              <th className="pb-3 font-medium text-right">Liquid</th>
              <th className="pb-3 font-medium text-right">Staked</th>
              <th className="pb-3 font-medium text-right">Total</th>
              <th className="pb-3 font-medium text-right">Txns</th>
            </tr>
          </thead>
          <tbody>
            {displayWallets.map((w, i) => (
              <tr key={i} className={`border-b border-slate-100 hover:bg-slate-50 ${w.hasStaking ? 'bg-blue-50/30' : ''}`}>
                <td className="py-3">
                  <div className="flex items-center gap-2">
                    <a 
                      href={`${EXPLORER_URLS[w.chain] || '#'}${w.account}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:underline font-mono text-xs flex items-center gap-1"
                    >
                      {w.account.length > 24 
                        ? `${w.account.slice(0, 12)}...${w.account.slice(-8)}`
                        : w.account
                      }
                      <ExternalLink className="w-3 h-3" />
                    </a>
                    {w.label && (
                      <span className="text-slate-500 text-xs">({w.label})</span>
                    )}
                  </div>
                  {w.stakingNote && (
                    <div className="text-xs text-blue-600 mt-1">{w.stakingNote}</div>
                  )}
                </td>
                <td className="py-3">
                  <span className={`px-2 py-1 rounded text-xs ${CHAIN_COLORS[w.chain] || 'bg-gray-100 text-gray-700'}`}>
                    {w.chainName}
                  </span>
                </td>
                <td className="py-3 text-right font-mono">
                  {w.liquidBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                </td>
                <td className="py-3 text-right font-mono text-blue-600">
                  {w.stakedBalance > 0 ? w.stakedBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 }) : '-'}
                </td>
                <td className="py-3 text-right font-mono font-semibold">
                  {w.totalBalance.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })} {w.symbol}
                </td>
                <td className="py-3 text-right text-slate-500">
                  {w.txCount.toLocaleString()}
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

      {/* Exchange Accounts Section */}
      {data.exchangeAccounts && data.exchangeAccounts.length > 0 && (
        <div className="mt-6 pt-6 border-t border-slate-200">
          <h3 className="text-lg font-semibold text-slate-800 mb-4 flex items-center gap-2">
            <Database className="w-5 h-5 text-amber-600" />
            Exchange Accounts
            <span className="text-xs font-normal text-slate-500 ml-2">
              (From imports)
            </span>
          </h3>
          <div className="grid gap-4 md:grid-cols-2">
            {data.exchangeAccounts.map((ex, i) => (
              <div key={i} className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="font-medium text-amber-900 capitalize">{ex.account}</span>
                  {ex.totalCad !== 0 && (
                    <span className="text-sm text-amber-700">
                      ~${ex.totalCad.toLocaleString()} CAD
                    </span>
                  )}
                </div>
                <div className="space-y-1">
                  {Object.entries(ex.balances).map(([asset, amount]) => (
                    <div key={asset} className="flex justify-between text-sm">
                      <span className="text-amber-800">{asset}</span>
                      <span className={`font-mono ${amount < 0 ? 'text-red-600' : 'text-amber-900'}`}>
                        {amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Note */}
      {data.note && (
        <div className="mt-4 text-xs text-slate-500 flex items-center gap-2">
          <CheckCircle className="w-4 h-4 text-green-500" />
          {data.note}
        </div>
      )}
    </div>
  );
}

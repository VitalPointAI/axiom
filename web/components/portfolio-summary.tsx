'use client';

import { useEffect, useState } from 'react';
import { Wallet, Coins, RefreshCw, ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react';

interface WalletBalance {
  account: string;
  liquid: number;
  staked: number;
}

interface TokenHolding {
  symbol: string;
  amount: number;
  price: number;
  value: number;
}

interface PortfolioData {
  totalValue: number;
  totalValueCad?: number;
  nearPrice?: number;
  cadRate?: number;
  walletCount: number;
  assetCount: number;
  liquid?: { near: number; usd: number; cad: number };
  staked?: { near: number; usd: number; cad: number };
  tokens?: { count: number; usd: number; cad: number };
  stakingRewards?: { near: number; usd: number };
  holdings?: TokenHolding[];
  walletBalances?: WalletBalance[];
  priceSource?: string;
  error?: string;
}

export function PortfolioSummary() {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const fetchData = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/portfolio');
      if (!res.ok) {
        if (res.status === 503) {
          const errData = await res.json();
          throw new Error(errData.message || 'Service temporarily unavailable');
        }
        throw new Error('Failed to fetch');
      }
      const json = await res.json();
      
      // Validate that we have a real price
      if (!json.nearPrice || json.nearPrice === 0) {
        throw new Error('Could not fetch NEAR price');
      }
      
      setData(json);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load portfolio data');
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
        <div className="flex items-center gap-2 text-amber-600 mb-2">
          <AlertTriangle className="w-5 h-5" />
          <span className="font-medium">Portfolio Load Error</span>
        </div>
        <p className="text-red-500">{error || 'No data available'}</p>
        <button onClick={fetchData} className="mt-2 text-sm text-blue-500 hover:underline">
          Retry
        </button>
      </div>
    );
  }

  const totalValue = data.totalValue ?? 0;
  const totalValueCad = data.totalValueCad ?? totalValue * 1.38;
  const nearPrice = data.nearPrice ?? 0;

  // If price is missing or zero, show warning
  if (!nearPrice || nearPrice === 0) {
    return (
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <div className="flex items-center gap-2 text-amber-600 mb-2">
          <AlertTriangle className="w-5 h-5" />
          <span className="font-medium">Price Data Unavailable</span>
        </div>
        <p className="text-slate-600">Could not fetch current NEAR price. Please try again.</p>
        <button onClick={fetchData} className="mt-2 text-sm text-blue-500 hover:underline">
          Retry
        </button>
      </div>
    );
  }

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

      {/* Main Value - Clickable to expand */}
      <button 
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left mb-4 hover:bg-slate-50 rounded-lg p-2 -m-2 transition"
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-4xl font-bold text-slate-900">
              ${totalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD
            </p>
            <p className="text-lg text-slate-600">
              CAD ${totalValueCad.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>
          {expanded ? (
            <ChevronUp className="w-5 h-5 text-slate-400" />
          ) : (
            <ChevronDown className="w-5 h-5 text-slate-400" />
          )}
        </div>
        <p className="text-sm text-slate-500 mt-1">
          NEAR: ${nearPrice.toFixed(2)} USD
          {data.priceSource && <span className="text-xs text-slate-400 ml-2">({data.priceSource})</span>}
          {' '}• Click to {expanded ? 'collapse' : 'expand'}
        </p>
      </button>

      {/* Expanded Breakdown */}
      {expanded && (
        <div className="border-t pt-4 mb-4 space-y-4">
          {/* Value Breakdown */}
          <div className="grid grid-cols-3 gap-3">
            {data.liquid && (
              <div className="bg-blue-50 rounded-lg p-3">
                <p className="text-lg font-bold text-blue-700">
                  {data.liquid.near.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </p>
                <p className="text-xs text-slate-600">Liquid NEAR</p>
                <p className="text-sm text-blue-600">${data.liquid.usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
              </div>
            )}
            {data.staked && data.staked.near > 0 && (
              <div className="bg-purple-50 rounded-lg p-3">
                <p className="text-lg font-bold text-purple-700">
                  {data.staked.near.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </p>
                <p className="text-xs text-slate-600">Staked NEAR</p>
                <p className="text-sm text-purple-600">${data.staked.usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
              </div>
            )}
            {data.tokens && data.tokens.count > 0 && (
              <div className="bg-green-50 rounded-lg p-3">
                <p className="text-lg font-bold text-green-700">{data.tokens.count}</p>
                <p className="text-xs text-slate-600">Other Tokens</p>
                <p className="text-sm text-green-600">${data.tokens.usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}</p>
              </div>
            )}
          </div>

          {/* Wallet Balances */}
          {data.walletBalances && data.walletBalances.length > 0 && (
            <div>
              <p className="text-sm font-medium text-slate-600 mb-2">Wallet Balances</p>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {data.walletBalances.map((wallet, idx) => {
                  const totalNear = (wallet.liquid || 0) + (wallet.staked || 0);
                  const totalUsd = totalNear * nearPrice;
                  return (
                    <div key={wallet.account + idx} className="flex items-center justify-between p-2 bg-slate-50 rounded-lg text-sm">
                      <div className="flex items-center gap-2">
                        <Wallet className="w-4 h-4 text-slate-400" />
                        <span className="font-mono text-slate-700">
                          {wallet.account.length > 25 
                            ? wallet.account.slice(0, 12) + '...' + wallet.account.slice(-10)
                            : wallet.account}
                        </span>
                      </div>
                      <div className="text-right">
                        <p className="font-medium text-slate-900">
                          {totalNear.toLocaleString(undefined, { maximumFractionDigits: 2 })} NEAR
                        </p>
                        <p className="text-xs text-slate-500">
                          ${totalUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })} USD
                        </p>
                        {wallet.staked > 0.1 && (
                          <p className="text-xs text-purple-500">
                            ({wallet.staked.toLocaleString(undefined, { maximumFractionDigits: 0 })} staked)
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Top Token Holdings */}
          {data.holdings && data.holdings.length > 1 && (
            <div>
              <p className="text-sm font-medium text-slate-600 mb-2">Top Holdings</p>
              <div className="space-y-1">
                {data.holdings.slice(0, 8).map((holding, idx) => (
                  <div key={holding.symbol + idx} className="flex items-center justify-between py-1 text-sm">
                    <span className="font-medium text-slate-700">{holding.symbol}</span>
                    <div className="text-right">
                      <span className="text-slate-600">
                        {holding.amount.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </span>
                      <span className="text-slate-400 ml-2">
                        ${(holding.value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Quick Stats */}
      <div className="grid grid-cols-2 gap-4 pt-4 border-t">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-blue-50 rounded-lg">
            <Wallet className="w-4 h-4 text-blue-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900">{data.walletCount ?? 0}</p>
            <p className="text-xs text-slate-500">Wallets</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="p-2 bg-purple-50 rounded-lg">
            <Coins className="w-4 h-4 text-purple-600" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900">{data.assetCount ?? 0}</p>
            <p className="text-xs text-slate-500">Assets</p>
          </div>
        </div>
      </div>
    </div>
  );
}

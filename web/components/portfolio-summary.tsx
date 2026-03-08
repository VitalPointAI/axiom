'use client';

import { useEffect, useState } from 'react';
import { Wallet, Coins, RefreshCw, ChevronDown, ChevronUp, AlertTriangle, Building2, Flag, Lock } from 'lucide-react';

interface WalletBalance {
  account: string;
  liquid: number;
  staked: number;
}

interface TokenHolding {
  symbol: string;
  contract?: string;
  amount: number;
  price: number;
  value: number;
  source?: string;
}

interface ExchangeHolding {
  asset: string;
  balance: number;
}

interface Exchange {
  name: string;
  holdings: ExchangeHolding[];
}

interface StakingPosition {
  account: string;
  validator: string;
  staked: number;
}

interface PortfolioData {
  totalValue: number;
  totalValueCad?: number;
  nearPrice?: number;
  cadRate?: number;
  walletCount: number;
  assetCount: number;
  nearBalance?: number;
  stakingBalance?: number;
  totalNear?: number;
  liquid?: { near: number; usd: number; cad: number };
  staked?: { near: number; usd: number; cad: number };
  tokens?: { count: number; usd: number; cad: number };
  stakingRewards?: { near: number; usd: number };
  stakingPositions?: StakingPosition[];
  holdings?: TokenHolding[];
  walletBalances?: WalletBalance[];
  wallets?: WalletBalance[];
  exchanges?: {
    count: number;
    list: Exchange[];
    totalNear: number;
    totalUsdc: number;
    totalValueUsd: number;
    totalValueCad: number;
  };
  grandTotal?: {
    usd: number;
    cad: number;
    includesExchanges: boolean;
  };
  priceSource?: string;
  error?: string;
}

export function PortfolioSummary() {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [reportingSpam, setReportingSpam] = useState<string | null>(null);
  const [spamReported, setSpamReported] = useState<Set<string>>(new Set());

  const reportSpam = async (symbol: string, contract?: string) => {
    if (!confirm(`Report "${symbol}" as spam?\n\nThis will hide it from your portfolio.`)) {
      return;
    }
    
    setReportingSpam(symbol);
    try {
      const res = await fetch('/api/spam', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          tokenSymbol: symbol, 
          tokenContract: contract,
          reason: 'User reported spam'
        })
      });
      
      if (res.ok) {
        setSpamReported(prev => new Set([...prev, symbol]));
        fetchData();
      } else {
        alert('Failed to report spam token');
      }
    } catch (err) {
      console.error('Error reporting spam:', err);
      alert('Failed to report spam token');
    } finally {
      setReportingSpam(null);
    }
  };

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
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6 animate-pulse">
        <div className="h-8 bg-slate-200 dark:bg-slate-700 rounded w-1/3 mb-4"></div>
        <div className="h-12 bg-slate-200 dark:bg-slate-700 rounded w-1/2 mb-2"></div>
        <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-1/4"></div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6">
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
  const cadRate = data.cadRate ?? 1.38;
  
  const displayValueUsd = data.grandTotal?.usd ?? totalValue;
  const displayValueCad = data.grandTotal?.cad ?? totalValueCad;
  const hasExchanges = data.exchanges && data.exchanges.count > 0;
  
  const liquidNear = data.nearBalance ?? 0;
  const stakedNear = data.stakingBalance ?? 0;
  const totalNear = data.totalNear ?? (liquidNear + stakedNear);

  if (!nearPrice || nearPrice === 0) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6">
        <div className="flex items-center gap-2 text-amber-600 mb-2">
          <AlertTriangle className="w-5 h-5" />
          <span className="font-medium">Price Data Unavailable</span>
        </div>
        <p className="text-slate-600 dark:text-slate-400">Could not fetch current NEAR price. Please try again.</p>
        <button onClick={fetchData} className="mt-2 text-sm text-blue-500 hover:underline">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-700 dark:text-slate-200">Portfolio Value</h2>
        <button 
          onClick={fetchData}
          className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition"
          title="Refresh"
        >
          <RefreshCw className="w-4 h-4 text-slate-400" />
        </button>
      </div>

      {/* Main Value - Clickable to expand */}
      <button 
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left mb-4 hover:bg-slate-50 dark:hover:bg-slate-700/50 rounded-lg p-2 -m-2 transition"
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-4xl font-bold text-slate-900 dark:text-white">
              ${displayValueUsd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD
            </p>
            <p className="text-lg text-slate-600 dark:text-slate-400">
              CAD ${displayValueCad.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
          </div>
          {expanded ? (
            <ChevronUp className="w-5 h-5 text-slate-400" />
          ) : (
            <ChevronDown className="w-5 h-5 text-slate-400" />
          )}
        </div>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          NEAR: ${nearPrice.toFixed(2)} USD
          {data.priceSource && <span className="text-xs text-slate-400 ml-2">({data.priceSource})</span>}
          {hasExchanges && <span className="text-xs text-green-600 ml-2">• Includes exchange holdings</span>}
          {' '}• Click to {expanded ? 'collapse' : 'expand'}
        </p>
      </button>

      {/* Expanded Breakdown */}
      {expanded && (
        <div className="border-t border-slate-200 dark:border-slate-600 pt-4 mb-4 space-y-4">
          {/* Value Breakdown */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-blue-50 dark:bg-blue-900/30 rounded-lg p-3">
              <p className="text-lg font-bold text-blue-700 dark:text-blue-400">
                {liquidNear.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </p>
              <p className="text-xs text-slate-600 dark:text-slate-400">Liquid NEAR</p>
              <p className="text-sm text-blue-600 dark:text-blue-400">
                ${(liquidNear * nearPrice).toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </p>
            </div>
            {stakedNear > 0 && (
              <div className="bg-purple-50 dark:bg-purple-900/30 rounded-lg p-3">
                <p className="text-lg font-bold text-purple-700 dark:text-purple-400">
                  {stakedNear.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                </p>
                <p className="text-xs text-slate-600 dark:text-slate-400">Staked NEAR</p>
                <p className="text-sm text-purple-600 dark:text-purple-400">
                  ${(stakedNear * nearPrice).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </p>
              </div>
            )}
            {data.holdings && data.holdings.length > 1 && (
              <div className="bg-green-50 dark:bg-green-900/30 rounded-lg p-3">
                <p className="text-lg font-bold text-green-700 dark:text-green-400">{data.holdings.length - 1}</p>
                <p className="text-xs text-slate-600 dark:text-slate-400">Other Tokens</p>
                <p className="text-sm text-green-600 dark:text-green-400">
                  ${data.holdings.slice(1).reduce((sum, h) => sum + (h.value || 0), 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </p>
              </div>
            )}
          </div>

          {/* STAKING SECTION */}
          {data.stakingPositions && data.stakingPositions.length > 0 && (
            <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <Lock className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                <p className="text-sm font-medium text-purple-800 dark:text-purple-300">Staking by Validator</p>
                <span className="text-xs text-purple-600 dark:text-purple-400 ml-auto">
                  {stakedNear.toLocaleString(undefined, { maximumFractionDigits: 2 })} NEAR total
                </span>
              </div>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {data.stakingPositions.map((pos, idx) => {
                  const valueUsd = pos.staked * nearPrice;
                  const validatorName = pos.validator
                    .replace('.poolv1.near', '')
                    .replace('.pool.near', '')
                    .replace('.near', '');
                  return (
                    <div key={pos.account + pos.validator + idx} className="flex justify-between items-center text-sm py-1">
                      <div className="flex flex-col truncate max-w-[55%]">
                        <span className="text-purple-800 dark:text-purple-200 font-medium truncate text-xs" title={pos.account}>
                          {pos.account.replace('.near', '')}
                        </span>
                        <span className="text-purple-500 dark:text-purple-400 text-xs truncate" title={pos.validator}>
                          → {validatorName}
                        </span>
                      </div>
                      <div className="text-right">
                        <span className="text-purple-600 dark:text-purple-400">
                          {pos.staked.toLocaleString(undefined, { maximumFractionDigits: 2 })} NEAR
                        </span>
                        <span className="text-purple-500/70 dark:text-purple-500 text-xs ml-2">
                          ${valueUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="border-t border-purple-200 dark:border-purple-700 mt-2 pt-2 flex justify-between text-sm">
                <span className="text-purple-700 dark:text-purple-300">Staking Total</span>
                <span className="font-bold text-purple-800 dark:text-purple-200">
                  ${(stakedNear * nearPrice).toLocaleString(undefined, { maximumFractionDigits: 0 })} USD
                </span>
              </div>
            </div>
          )}

          {/* Exchange Holdings */}
          {hasExchanges && data.exchanges && (
            <div className="bg-amber-50 dark:bg-amber-900/20 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <Building2 className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                <p className="text-sm font-medium text-amber-800 dark:text-amber-300">Exchange Holdings</p>
              </div>
              <div className="space-y-2">
                {data.exchanges.list.map((ex, idx) => (
                  <div key={idx} className="flex justify-between items-center text-sm">
                    <span className="text-amber-700 dark:text-amber-300 font-medium">{ex.name}</span>
                    <div className="text-right">
                      {ex.holdings.slice(0, 3).map((h, hIdx) => (
                        <span key={hIdx} className="text-amber-600 dark:text-amber-400 ml-2">
                          {h.balance.toLocaleString(undefined, { maximumFractionDigits: 2 })} {h.asset}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
              <div className="border-t border-amber-200 dark:border-amber-700 mt-2 pt-2 flex justify-between text-sm">
                <span className="text-amber-700 dark:text-amber-300">Exchange Total</span>
                <span className="font-bold text-amber-800 dark:text-amber-200">
                  ${data.exchanges.totalValueUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })} USD
                </span>
              </div>
            </div>
          )}

          {/* Wallet Balances */}
          {data.wallets && data.wallets.length > 0 && (
            <div>
              <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">Wallet Balances</p>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {data.wallets.map((wallet, idx) => {
                  const totalWalletNear = (wallet.liquid || 0) + (wallet.staked || 0);
                  const totalUsd = totalWalletNear * nearPrice;
                  return (
                    <div key={wallet.account + idx} className="flex items-center justify-between p-2 bg-slate-50 dark:bg-slate-700/50 rounded-lg text-sm">
                      <div className="flex items-center gap-2">
                        <Wallet className="w-4 h-4 text-slate-400" />
                        <span className="font-mono text-slate-700 dark:text-slate-300">
                          {wallet.account.length > 25 
                            ? wallet.account.slice(0, 12) + '...' + wallet.account.slice(-10)
                            : wallet.account}
                        </span>
                      </div>
                      <div className="text-right">
                        <p className="font-medium text-slate-900 dark:text-white">
                          {totalWalletNear.toLocaleString(undefined, { maximumFractionDigits: 2 })} NEAR
                        </p>
                        <p className="text-xs text-slate-500">
                          ${totalUsd.toLocaleString(undefined, { maximumFractionDigits: 0 })} USD
                        </p>
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
              <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">Top Holdings</p>
              <div className="space-y-1">
                {data.holdings.slice(0, 8).map((holding, idx) => (
                  <div key={holding.symbol + idx} className="flex items-center justify-between py-1 text-sm group">
                    <div className="flex items-center gap-1">
                      <span className="font-medium text-slate-700 dark:text-slate-300">{holding.symbol}</span>
                      {holding.symbol !== 'NEAR' && !spamReported.has(holding.symbol) && (
                        <button
                          onClick={() => reportSpam(holding.symbol, holding.contract)}
                          disabled={reportingSpam === holding.symbol}
                          className="opacity-0 group-hover:opacity-100 transition-opacity ml-1 text-slate-400 hover:text-red-500"
                          title="Report as spam"
                        >
                          {reportingSpam === holding.symbol ? (
                            <RefreshCw className="w-3 h-3 animate-spin" />
                          ) : (
                            <Flag className="w-3 h-3" />
                          )}
                        </button>
                      )}
                    </div>
                    <div className="text-right">
                      <span className="text-slate-600 dark:text-slate-400">
                        {holding.amount.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </span>
                      <span className="text-slate-400 dark:text-slate-500 ml-2">
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
      <div className="grid grid-cols-2 gap-4 pt-4 border-t border-slate-200 dark:border-slate-600">
        <div className="flex items-center gap-2">
          <div className="p-2 bg-blue-50 dark:bg-blue-900/30 rounded-lg">
            <Wallet className="w-4 h-4 text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900 dark:text-white">{data.walletCount ?? 0}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">Wallets</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="p-2 bg-purple-50 dark:bg-purple-900/30 rounded-lg">
            <Coins className="w-4 h-4 text-purple-600 dark:text-purple-400" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900 dark:text-white">{data.assetCount ?? 0}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">Assets</p>
          </div>
        </div>
      </div>

      {/* Exchange indicator */}
      {hasExchanges && (
        <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-600">
          <div className="flex items-center gap-2 text-sm text-amber-600 dark:text-amber-400">
            <Building2 className="w-4 h-4" />
            <span>{data.exchanges?.count} exchange import{data.exchanges?.count !== 1 ? 's' : ''} included</span>
          </div>
        </div>
      )}
    </div>
  );
}

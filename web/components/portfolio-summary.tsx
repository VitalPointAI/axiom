'use client';

import { useEffect, useState } from 'react';
import { Wallet, Coins, RefreshCw, ChevronDown, ChevronUp, AlertTriangle, Lock } from 'lucide-react';
import { apiClient, ApiError } from '@/lib/api';

// FastAPI /api/portfolio/summary response types
interface HoldingResponse {
  token_symbol: string;
  chain: string;
  total_units: number;
  acb_per_unit_cad: number;
  total_cost_cad: number;
  as_of_date: string;
}

interface StakingPositionResponse {
  wallet_id: number;
  account_id: string;
  validator_id: string;
  staked_balance: number;
  chain: string;
}

interface PortfolioSummaryResponse {
  holdings: HoldingResponse[];
  staking_positions: StakingPositionResponse[];
}

export function PortfolioSummary() {
  const [data, setData] = useState<PortfolioSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.get<PortfolioSummaryResponse>('/api/portfolio/summary');
      setData(res);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(`Failed to load portfolio (${err.status})`);
      } else {
        setError('Failed to load portfolio data');
      }
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

  const holdings = data.holdings || [];
  const stakingPositions = data.staking_positions || [];

  const totalCostCad = holdings.reduce((sum, h) => sum + (h.total_cost_cad || 0), 0);
  const assetCount = holdings.length;

  // Find NEAR holding for display
  const nearHolding = holdings.find((h) => h.token_symbol === 'NEAR');
  const totalNearUnits = nearHolding?.total_units ?? 0;

  const formatCad = (n: number) =>
    '$' + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

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

      {/* Main Value */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left mb-4 hover:bg-slate-50 dark:hover:bg-slate-700/50 rounded-lg p-2 -m-2 transition"
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="text-4xl font-bold text-slate-900 dark:text-white">
              {formatCad(totalCostCad)} CAD
            </p>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              Cost basis (ACB)
              {nearHolding && (
                <span className="ml-2 text-xs">
                  • {totalNearUnits.toLocaleString(undefined, { maximumFractionDigits: 2 })} NEAR
                </span>
              )}
            </p>
          </div>
          {expanded ? (
            <ChevronUp className="w-5 h-5 text-slate-400" />
          ) : (
            <ChevronDown className="w-5 h-5 text-slate-400" />
          )}
        </div>
        <p className="text-xs text-slate-400 mt-1">Click to {expanded ? 'collapse' : 'expand'}</p>
      </button>

      {/* Expanded Holdings */}
      {expanded && holdings.length > 0 && (
        <div className="border-t border-slate-200 dark:border-slate-600 pt-4 mb-4 space-y-4">
          {/* Holdings table */}
          <div>
            <p className="text-sm font-medium text-slate-600 dark:text-slate-400 mb-2">Holdings (ACB)</p>
            <div className="space-y-1">
              {holdings.slice(0, 10).map((h, idx) => (
                <div
                  key={h.token_symbol + h.chain + idx}
                  className="flex items-center justify-between py-1 text-sm"
                >
                  <div className="flex flex-col">
                    <span className="font-medium text-slate-700 dark:text-slate-300">
                      {h.token_symbol}
                    </span>
                    <span className="text-xs text-slate-400">{h.chain}</span>
                  </div>
                  <div className="text-right">
                    <span className="text-slate-600 dark:text-slate-400">
                      {(h.total_units ?? 0).toLocaleString(undefined, { maximumFractionDigits: 4 })}
                    </span>
                    <span className="text-slate-400 dark:text-slate-500 ml-2">
                      {formatCad(h.total_cost_cad ?? 0)}
                    </span>
                  </div>
                </div>
              ))}
              {holdings.length > 10 && (
                <p className="text-xs text-slate-400 text-center pt-1">
                  +{holdings.length - 10} more assets
                </p>
              )}
            </div>
          </div>

          {/* Staking positions */}
          {stakingPositions.length > 0 && (
            <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-3">
                <Lock className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                <p className="text-sm font-medium text-purple-800 dark:text-purple-300">
                  Staking Positions
                </p>
              </div>
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {stakingPositions.map((pos, idx) => {
                  const validatorName = pos.validator_id
                    .replace('.poolv1.near', '')
                    .replace('.pool.near', '')
                    .replace('.near', '');
                  return (
                    <div
                      key={pos.account_id + pos.validator_id + idx}
                      className="flex justify-between items-center text-sm py-1"
                    >
                      <div className="flex flex-col truncate max-w-[55%]">
                        <span
                          className="text-purple-800 dark:text-purple-200 font-medium truncate text-xs"
                          title={pos.account_id}
                        >
                          {pos.account_id.replace('.near', '')}
                        </span>
                        <span
                          className="text-purple-500 dark:text-purple-400 text-xs truncate"
                          title={pos.validator_id}
                        >
                          → {validatorName}
                        </span>
                      </div>
                      <span className="text-purple-600 dark:text-purple-400">
                        {(pos.staked_balance ?? 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}{' '}
                        NEAR
                      </span>
                    </div>
                  );
                })}
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
            <p className="text-2xl font-bold text-slate-900 dark:text-white">
              {stakingPositions.length}
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400">Staking positions</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="p-2 bg-purple-50 dark:bg-purple-900/30 rounded-lg">
            <Coins className="w-4 h-4 text-purple-600 dark:text-purple-400" />
          </div>
          <div>
            <p className="text-2xl font-bold text-slate-900 dark:text-white">{assetCount}</p>
            <p className="text-xs text-slate-500 dark:text-slate-400">Assets</p>
          </div>
        </div>
      </div>
    </div>
  );
}

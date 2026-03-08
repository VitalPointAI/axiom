'use client';

import { useState, useEffect } from 'react';
import { Coins, TrendingUp, ExternalLink } from 'lucide-react';

interface StakingPosition {
  chain: string;
  chainSymbol: string;
  address: string;
  label: string;
  stakedAmount: number;
  pendingRewards: number;
  validators: string[];
  totalValue: number;
}

interface MultichainStakingData {
  positions: StakingPosition[];
  totals: {
    totalStaked: number;
    totalPendingRewards: number;
    totalValue: number;
    chainCount: number;
  };
}

const CHAIN_COLORS: Record<string, string> = {
  'Akash': 'bg-red-500',
  'Crypto.org': 'bg-blue-500',
  'Cosmos': 'bg-purple-500',
};

const CHAIN_EXPLORERS: Record<string, string> = {
  'Akash': 'https://www.mintscan.io/akash/account/',
  'Crypto.org': 'https://crypto.org/explorer/account/',
};

export function MultichainStaking() {
  const [data, setData] = useState<MultichainStakingData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const res = await fetch('/api/staking/multichain');
      const json = await res.json();
      setData(json);
    } catch (e) {
      console.error('Failed to fetch multichain staking:', e);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-slate-800 rounded-lg p-6">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <Coins className="w-5 h-5" />
          Multi-Chain Staking
        </h2>
        <div className="text-gray-400">Loading...</div>
      </div>
    );
  }

  if (!data || data.positions.length === 0) {
    return null; // Don't show section if no multi-chain staking
  }

  const formatAmount = (n: number, decimals = 2) => 
    n?.toLocaleString(undefined, { maximumFractionDigits: decimals }) || '0';

  return (
    <div className="bg-slate-800 rounded-lg p-6 space-y-4">
      <h2 className="text-xl font-semibold flex items-center gap-2">
        <Coins className="w-5 h-5 text-orange-400" />
        Multi-Chain Staking
      </h2>

      {/* Summary */}
      <div className="grid grid-cols-3 gap-4 bg-slate-700/50 rounded-lg p-4">
        <div>
          <div className="text-sm text-gray-400">Total Staked</div>
          <div className="text-lg font-semibold text-white">
            {data.totals.chainCount} chains
          </div>
        </div>
        <div>
          <div className="text-sm text-gray-400">Pending Rewards</div>
          <div className="text-lg font-semibold text-green-400">
            {formatAmount(data.totals.totalPendingRewards)} tokens
          </div>
        </div>
        <div>
          <div className="text-sm text-gray-400">Positions</div>
          <div className="text-lg font-semibold text-white">
            {data.positions.length}
          </div>
        </div>
      </div>

      {/* Positions */}
      <div className="space-y-3">
        {data.positions.map((pos, i) => (
          <div key={i} className="bg-slate-700/50 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${CHAIN_COLORS[pos.chain] || 'bg-gray-500'}`} />
                <span className="font-medium">{pos.chain}</span>
                <span className="text-gray-400 text-sm">({pos.chainSymbol})</span>
              </div>
              {CHAIN_EXPLORERS[pos.chain] && (
                <a 
                  href={`${CHAIN_EXPLORERS[pos.chain]}${pos.address}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-400 hover:text-blue-300 text-sm flex items-center gap-1"
                >
                  Explorer <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
            
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <div className="text-gray-400">Staked</div>
                <div className="font-medium">{formatAmount(pos.stakedAmount)} {pos.chainSymbol}</div>
              </div>
              <div>
                <div className="text-gray-400">Pending Rewards</div>
                <div className="font-medium text-green-400 flex items-center gap-1">
                  <TrendingUp className="w-3 h-3" />
                  {formatAmount(pos.pendingRewards)} {pos.chainSymbol}
                </div>
              </div>
              <div>
                <div className="text-gray-400">Total</div>
                <div className="font-medium">{formatAmount(pos.totalValue)} {pos.chainSymbol}</div>
              </div>
            </div>

            {pos.validators.length > 0 && (
              <div className="mt-2 text-xs text-gray-500">
                Validator: {pos.validators[0].slice(0, 20)}...
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

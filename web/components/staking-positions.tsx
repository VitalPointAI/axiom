'use client';

import { useEffect, useState } from 'react';
import { Coins, TrendingUp, Server } from 'lucide-react';

interface StakingPosition {
  validator: string;
  staked: number;
  rewards: number;
  value: number;
}

export function StakingPositions() {
  const [positions, setPositions] = useState<StakingPosition[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/portfolio')
      .then(res => res.json())
      .then(data => {
        setPositions(data.staking || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <h2 className="text-lg font-semibold text-slate-700 mb-4">Staking Positions</h2>
        <div className="animate-pulse space-y-3">
          <div className="h-16 bg-slate-200 rounded"></div>
          <div className="h-16 bg-slate-200 rounded"></div>
        </div>
      </div>
    );
  }

  const totalStaked = positions.reduce((sum, p) => sum + p.staked, 0);
  const totalRewards = positions.reduce((sum, p) => sum + p.rewards, 0);
  const totalValue = positions.reduce((sum, p) => sum + p.value, 0);

  return (
    <div className="bg-white rounded-lg shadow-sm border p-6">
      <h2 className="text-lg font-semibold text-slate-700 mb-4">Staking Positions</h2>

      {positions.length === 0 ? (
        <div className="text-center py-8 text-slate-500">
          <Server className="w-12 h-12 mx-auto mb-3 text-slate-300" />
          <p>No staking positions</p>
          <p className="text-sm">Stake NEAR to earn rewards</p>
        </div>
      ) : (
        <>
          {/* Summary */}
          <div className="grid grid-cols-3 gap-4 mb-6 p-4 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg">
            <div className="text-center">
              <p className="text-2xl font-bold text-slate-900">
                {totalStaked.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </p>
              <p className="text-xs text-slate-500">NEAR Staked</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-green-600">
                +{totalRewards.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </p>
              <p className="text-xs text-slate-500">Rewards Earned</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-slate-900">
                ${totalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
              <p className="text-xs text-slate-500">Total Value</p>
            </div>
          </div>

          {/* Validator list */}
          <div className="space-y-3">
            {positions.map((pos) => (
              <div 
                key={pos.validator}
                className="flex items-center justify-between p-4 border rounded-lg hover:bg-slate-50 transition"
              >
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-blue-100 rounded-lg">
                    <Server className="w-5 h-5 text-blue-600" />
                  </div>
                  <div>
                    <p className="font-medium text-slate-800">
                      {pos.validator.replace('.pool.near', '')}
                    </p>
                    <p className="text-xs text-slate-500">.pool.near</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="font-medium text-slate-900">
                    {pos.staked.toLocaleString(undefined, { maximumFractionDigits: 2 })} NEAR
                  </p>
                  <div className="flex items-center justify-end gap-1 text-green-600">
                    <TrendingUp className="w-3 h-3" />
                    <span className="text-xs">
                      +{pos.rewards.toLocaleString(undefined, { maximumFractionDigits: 4 })} rewards
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* APY estimate */}
          <div className="mt-4 pt-4 border-t text-center">
            <p className="text-sm text-slate-500">
              Estimated APY: <span className="font-medium text-green-600">~9-11%</span>
            </p>
          </div>
        </>
      )}
    </div>
  );
}

'use client';

import { useEffect, useState } from 'react';
import { TrendingUp, Server } from 'lucide-react';

interface StakingPosition {
  validator: string;
  staked: number;
  rewards: number;
  value: number;
}

interface PortfolioData {
  staking: StakingPosition[];
  stakingRewards?: { near: number; usd: number };
  staked?: { near: number; usd: number };
  nearPrice?: number;
}

export function StakingPositions() {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/portfolio')
      .then(res => res.json())
      .then(json => {
        setData(json);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <h2 className="text-lg font-semibold text-slate-700 mb-4">Staking</h2>
        <div className="animate-pulse space-y-3">
          <div className="h-16 bg-slate-200 rounded"></div>
        </div>
      </div>
    );
  }

  const positions = data?.staking || [];
  const totalStakedLive = data?.staked?.near || 0;
  const totalRewards = data?.stakingRewards?.near || 0;
  const nearPrice = data?.nearPrice || 5;

  const positionStaked = positions.reduce((sum, p) => sum + (p.staked || 0), 0);
  const positionRewards = positions.reduce((sum, p) => sum + (p.rewards || 0), 0);
  
  const displayStaked = totalStakedLive > 0 ? totalStakedLive : positionStaked;
  const displayRewards = totalRewards > 0 ? totalRewards : positionRewards;
  const totalValue = displayStaked * nearPrice;

  const formatUsd = (val: number) => "$" + val.toLocaleString(undefined, { maximumFractionDigits: 0 });

  return (
    <div className="bg-white rounded-lg shadow-sm border p-6">
      <h2 className="text-lg font-semibold text-slate-700 mb-4">Staking</h2>

      {positions.length === 0 && displayStaked === 0 ? (
        <div className="text-center py-8 text-slate-500">
          <Server className="w-12 h-12 mx-auto mb-3 text-slate-300" />
          <p>No staking positions</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-4 mb-6 p-4 bg-gradient-to-r from-blue-50 to-purple-50 rounded-lg">
            <div className="text-center">
              <p className="text-2xl font-bold text-slate-900">
                {displayStaked.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </p>
              <p className="text-xs text-slate-500">NEAR Staked</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-green-600">
                +{displayRewards.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </p>
              <p className="text-xs text-slate-500">Rewards Earned</p>
            </div>
            <div className="text-center">
              <p className="text-2xl font-bold text-slate-900">
                {formatUsd(totalValue)}
              </p>
              <p className="text-xs text-slate-500">Value (USD)</p>
            </div>
          </div>

          {positions.length > 0 && (
            <div className="space-y-3">
              <p className="text-sm font-medium text-slate-600">By Validator</p>
              {positions.map((pos, idx) => (
                <div key={pos.validator + idx} className="flex items-center justify-between p-3 border rounded-lg">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-blue-100 rounded-lg">
                      <Server className="w-4 h-4 text-blue-600" />
                    </div>
                    <p className="font-medium text-slate-800 text-sm">
                      {pos.validator.replace(".pool.near", "").replace(".poolv1.near", "").replace("meta-pool.near", "Meta Pool")}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-medium text-slate-900">
                      {(pos.staked || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })} NEAR
                    </p>
                    {(pos.rewards || 0) > 0 && (
                      <p className="text-xs text-green-600">+{(pos.rewards || 0).toFixed(2)} earned</p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

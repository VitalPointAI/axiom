// Component: components/staking-rewards-table.tsx
// Display per-epoch staking rewards with filtering

'use client';

import { useState, useEffect } from 'react';
import { Download, RefreshCw, TrendingUp, Calendar, Coins } from 'lucide-react';

interface EpochReward {
  id: number;
  epoch_id: number;
  epoch_date: string;
  account_id: string;
  validator_id: string;
  reward_near: number;
  reward_usd: number | null;
  reward_cad: number | null;
  near_price_usd: number | null;
}

interface RewardsSummary {
  total_near: number;
  total_usd: number;
  total_cad: number;
  epoch_count: number;
  first_epoch: string;
  last_epoch: string;
}

interface ValidatorSummary {
  validator_id: string;
  total_near: number;
  total_usd: number;
  total_cad: number;
  epoch_count: number;
}

interface Props {
  year?: string;
  showDownload?: boolean;
}

export function StakingRewardsTable({ year = '2025', showDownload = true }: Props) {
  const [rewards, setRewards] = useState<EpochReward[]>([]);
  const [summary, setSummary] = useState<RewardsSummary | null>(null);
  const [byValidator, setByValidator] = useState<ValidatorSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedValidator, setSelectedValidator] = useState<string>('');

  useEffect(() => {
    fetchRewards();
  }, [year, selectedValidator]);

  const fetchRewards = async () => {
    setLoading(true);
    try {
      let url = `/api/staking/rewards?year=${year}`;
      if (selectedValidator) {
        url += `&validator=${encodeURIComponent(selectedValidator)}`;
      }
      const res = await fetch(url);
      const data = await res.json();
      setRewards(data.rewards || []);
      setSummary(data.summary || null);
      setByValidator(data.byValidator || []);
    } catch (err) {
      console.error('Failed to fetch staking rewards:', err);
    } finally {
      setLoading(false);
    }
  };

  const downloadCsv = () => {
    let url = `/api/staking/rewards?year=${year}&format=csv`;
    if (selectedValidator) {
      url += `&validator=${encodeURIComponent(selectedValidator)}`;
    }
    window.open(url, '_blank');
  };

  const formatNear = (n: number) => (n || 0).toFixed(5);
  const formatCad = (n: number | null) => n != null ? `$${n.toFixed(2)}` : '-';
  const formatDate = (d: string) => {
    if (!d) return '-';
    return new Date(d).toLocaleDateString('en-CA');
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-32">
        <RefreshCw className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-green-50 rounded-lg p-4">
            <div className="flex items-center gap-2 text-sm text-green-600 font-medium">
              <Coins className="w-4 h-4" />
              Total Rewards
            </div>
            <div className="text-2xl font-bold text-green-900">
              {formatNear(summary.total_near)} NEAR
            </div>
            <div className="text-sm text-green-600">
              {formatCad(summary.total_cad)} CAD
            </div>
          </div>
          
          <div className="bg-blue-50 rounded-lg p-4">
            <div className="flex items-center gap-2 text-sm text-blue-600 font-medium">
              <TrendingUp className="w-4 h-4" />
              USD Value
            </div>
            <div className="text-2xl font-bold text-blue-900">
              ${(summary.total_usd || 0).toFixed(2)}
            </div>
            <div className="text-sm text-blue-600">
              At time of receipt
            </div>
          </div>
          
          <div className="bg-purple-50 rounded-lg p-4">
            <div className="flex items-center gap-2 text-sm text-purple-600 font-medium">
              <Calendar className="w-4 h-4" />
              Epochs
            </div>
            <div className="text-2xl font-bold text-purple-900">
              {summary.epoch_count}
            </div>
            <div className="text-sm text-purple-600">
              ~{Math.round(summary.epoch_count / 2)} days
            </div>
          </div>
          
          <div className="bg-slate-50 rounded-lg p-4">
            <div className="text-sm text-slate-600 font-medium">Period</div>
            <div className="text-lg font-bold text-slate-900">
              {formatDate(summary.first_epoch)}
            </div>
            <div className="text-sm text-slate-600">
              to {formatDate(summary.last_epoch)}
            </div>
          </div>
        </div>
      )}

      {/* By Validator */}
      {byValidator.length > 0 && (
        <div className="bg-white border rounded-lg p-4">
          <h3 className="font-semibold mb-3">By Validator</h3>
          <div className="space-y-2">
            {byValidator.map((v) => (
              <button
                key={v.validator_id}
                onClick={() => setSelectedValidator(
                  selectedValidator === v.validator_id ? '' : v.validator_id
                )}
                className={`w-full flex items-center justify-between p-3 rounded-lg transition-colors ${
                  selectedValidator === v.validator_id 
                    ? 'bg-blue-100 border-blue-300 border' 
                    : 'bg-slate-50 hover:bg-slate-100'
                }`}
              >
                <div className="text-left">
                  <div className="font-medium">{v.validator_id}</div>
                  <div className="text-sm text-slate-500">{v.epoch_count} epochs</div>
                </div>
                <div className="text-right">
                  <div className="font-bold">{formatNear(v.total_near)} NEAR</div>
                  <div className="text-sm text-slate-600">{formatCad(v.total_cad)}</div>
                </div>
              </button>
            ))}
          </div>
          {selectedValidator && (
            <button
              onClick={() => setSelectedValidator('')}
              className="mt-2 text-sm text-blue-600 hover:underline"
            >
              Clear filter
            </button>
          )}
        </div>
      )}

      {/* Actions */}
      {showDownload && rewards.length > 0 && (
        <div className="flex justify-end">
          <button
            onClick={downloadCsv}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
          >
            <Download className="w-4 h-4" />
            Export CSV for Tax Filing
          </button>
        </div>
      )}

      {/* Rewards Table */}
      {rewards.length > 0 ? (
        <div className="bg-white border rounded-lg overflow-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 sticky top-0">
              <tr>
                <th className="text-left px-4 py-3">Date</th>
                <th className="text-left px-4 py-3">Epoch</th>
                <th className="text-left px-4 py-3">Wallet</th>
                <th className="text-left px-4 py-3">Validator</th>
                <th className="text-right px-4 py-3">Reward (NEAR)</th>
                <th className="text-right px-4 py-3">Price</th>
                <th className="text-right px-4 py-3">Value (USD)</th>
                <th className="text-right px-4 py-3">Value (CAD)</th>
              </tr>
            </thead>
            <tbody>
              {rewards.map((r) => (
                <tr key={r.id} className="border-t hover:bg-slate-50">
                  <td className="px-4 py-3">{formatDate(r.epoch_date)}</td>
                  <td className="px-4 py-3 text-slate-500">{r.epoch_id}</td>
                  <td className="px-4 py-3 font-mono text-xs">{r.account_id}</td>
                  <td className="px-4 py-3 font-mono text-xs">{r.validator_id}</td>
                  <td className="px-4 py-3 text-right font-medium text-green-700">
                    {formatNear(r.reward_near)}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-500">
                    ${r.near_price_usd?.toFixed(2) || '-'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {r.reward_usd != null ? `$${r.reward_usd.toFixed(2)}` : '-'}
                  </td>
                  <td className="px-4 py-3 text-right font-medium">
                    {formatCad(r.reward_cad)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          
          {rewards.length >= 500 && (
            <div className="text-center py-3 text-sm text-slate-500 border-t">
              Showing first 500 rewards. Download CSV for complete data.
            </div>
          )}
        </div>
      ) : (
        <div className="bg-slate-50 rounded-lg p-8 text-center text-slate-500">
          <Coins className="w-12 h-12 mx-auto mb-3 text-slate-300" />
          <p>No staking rewards found for {year}</p>
          <p className="text-sm mt-1">
            Rewards are calculated from epoch balance snapshots
          </p>
        </div>
      )}
    </div>
  );
}

export default StakingRewardsTable;

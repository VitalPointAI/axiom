'use client';

import { useState, useEffect } from 'react';
import { ValidatorTracking } from '@/components/validator-tracking';
import { TrendingUp, Building2 } from 'lucide-react';

interface StakingSummary {
  tax_year: number;
  total_near: number;
  total_usd: number;
  total_cad: number;
  days: number;
}

interface ValidatorSummary {
  validator: string;
  total_near: number;
  total_usd: number;
  total_cad: number;
  start_date: string;
  end_date: string;
}

interface MonthlyData {
  month: string;
  total_near: number;
  total_usd: number;
  total_cad: number;
}

function StakingRewards() {
  const [summary, setSummary] = useState<StakingSummary[]>([]);
  const [byValidator, setByValidator] = useState<ValidatorSummary[]>([]);
  const [monthly, setMonthly] = useState<MonthlyData[]>([]);
  const [totals, setTotals] = useState<any>(null);
  const [selectedYear, setSelectedYear] = useState<string>('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, [selectedYear]);

  const fetchData = async () => {
    setLoading(true);
    const url = selectedYear ? `/api/staking?year=${selectedYear}` : '/api/staking';
    const res = await fetch(url);
    const data = await res.json();
    setSummary(data.summary || []);
    setByValidator(data.byValidator || []);
    setMonthly(data.monthly || []);
    setTotals(data.totals);
    setLoading(false);
  };

  const formatNear = (n: number) => n?.toLocaleString(undefined, { maximumFractionDigits: 2 }) || '0';
  const formatCad = (n: number) => '$' + (n?.toLocaleString(undefined, { maximumFractionDigits: 2 }) || '0');

  const years = [2020, 2021, 2022, 2023, 2024, 2025, 2026];

  return (
    <div className="space-y-6">
      {/* Year Filter */}
      <div className="flex gap-2 flex-wrap">
        <button
          onClick={() => setSelectedYear('')}
          className={`px-4 py-2 rounded-lg transition ${!selectedYear ? 'bg-blue-600 text-white' : 'bg-slate-700 text-gray-300 hover:bg-slate-600'}`}
        >
          All Years
        </button>
        {years.map(y => (
          <button
            key={y}
            onClick={() => setSelectedYear(y.toString())}
            className={`px-4 py-2 rounded-lg transition ${selectedYear === y.toString() ? 'bg-blue-600 text-white' : 'bg-slate-700 text-gray-300 hover:bg-slate-600'}`}
          >
            {y}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-10 text-gray-400">Loading...</div>
      ) : (
        <>
          {/* Grand Totals */}
          {totals && (
            <div className="bg-gradient-to-r from-purple-600 to-blue-600 text-white rounded-lg p-6">
              <h2 className="text-xl font-semibold mb-4">Total Staking Income</h2>
              <div className="grid grid-cols-3 gap-4">
                <div>
                  <div className="text-3xl font-bold">{formatNear(totals.total_near)} NEAR</div>
                  <div className="text-sm opacity-80">Total Rewards</div>
                </div>
                <div>
                  <div className="text-3xl font-bold">{formatCad(totals.total_cad)}</div>
                  <div className="text-sm opacity-80">CAD Value</div>
                </div>
                <div>
                  <div className="text-3xl font-bold">{totals.total_days?.toLocaleString()}</div>
                  <div className="text-sm opacity-80">Days Tracked</div>
                </div>
              </div>
            </div>
          )}

          {/* By Year Summary */}
          {!selectedYear && summary.length > 0 && (
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <h2 className="text-xl font-semibold mb-4 text-white">Income by Tax Year</h2>
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-2 text-gray-400">Year</th>
                    <th className="text-right py-2 text-gray-400">NEAR Rewards</th>
                    <th className="text-right py-2 text-gray-400">USD</th>
                    <th className="text-right py-2 text-gray-400">CAD</th>
                    <th className="text-right py-2 text-gray-400">Days</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.map(row => (
                    <tr key={row.tax_year} className="border-b border-slate-700 hover:bg-slate-700/50 cursor-pointer transition" onClick={() => setSelectedYear(row.tax_year.toString())}>
                      <td className="py-2 font-medium text-white">{row.tax_year}</td>
                      <td className="text-right text-white">{formatNear(row.total_near)}</td>
                      <td className="text-right text-gray-300">${formatNear(row.total_usd)}</td>
                      <td className="text-right font-semibold text-white">{formatCad(row.total_cad)}</td>
                      <td className="text-right text-gray-500">{row.days}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* By Validator */}
          <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
            <h2 className="text-xl font-semibold mb-4 text-white">
              {selectedYear ? `${selectedYear} Income by Validator` : 'All-Time Income by Validator'}
            </h2>
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left py-2 text-gray-400">Validator</th>
                  <th className="text-right py-2 text-gray-400">NEAR</th>
                  <th className="text-right py-2 text-gray-400">CAD</th>
                  <th className="text-right py-2 text-gray-400">Period</th>
                </tr>
              </thead>
              <tbody>
                {byValidator.map(row => (
                  <tr key={row.validator} className="border-b border-slate-700 hover:bg-slate-700/50 transition">
                    <td className="py-2 font-mono text-sm text-white">{row.validator}</td>
                    <td className="text-right text-white">{formatNear(row.total_near)}</td>
                    <td className="text-right font-semibold text-white">{formatCad(row.total_cad)}</td>
                    <td className="text-right text-gray-500 text-sm">
                      {row.start_date} → {row.end_date}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Monthly Breakdown */}
          {selectedYear && monthly.length > 0 && (
            <div className="bg-slate-800 rounded-lg p-6 border border-slate-700">
              <h2 className="text-xl font-semibold mb-4 text-white">{selectedYear} Monthly Breakdown</h2>
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700">
                    <th className="text-left py-2 text-gray-400">Month</th>
                    <th className="text-right py-2 text-gray-400">NEAR</th>
                    <th className="text-right py-2 text-gray-400">USD</th>
                    <th className="text-right py-2 text-gray-400">CAD</th>
                  </tr>
                </thead>
                <tbody>
                  {monthly.map(row => (
                    <tr key={row.month} className="border-b border-slate-700 hover:bg-slate-700/50 transition">
                      <td className="py-2 text-white">{row.month}</td>
                      <td className="text-right text-white">{formatNear(row.total_near)}</td>
                      <td className="text-right text-gray-300">${formatNear(row.total_usd)}</td>
                      <td className="text-right font-semibold text-white">{formatCad(row.total_cad)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Tax Note */}
          <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
            <p className="text-sm text-gray-400">
              <strong className="text-gray-300">💰 Tax Note:</strong> Staking rewards are generally treated as income 
              when received. The CAD values shown are based on the NEAR price at the time each reward was received.
            </p>
          </div>
        </>
      )}
    </div>
  );
}

export default function StakingPage() {
  const [activeTab, setActiveTab] = useState<'rewards' | 'validators'>('rewards');

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Staking</h1>
        <p className="text-gray-400 text-sm mt-1">
          Track your staking rewards and validator performance
        </p>
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-2 border-b border-slate-700 pb-0">
        <button
          onClick={() => setActiveTab('rewards')}
          className={`flex items-center gap-2 px-4 py-3 border-b-2 transition ${
            activeTab === 'rewards'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-gray-400 hover:text-gray-300'
          }`}
        >
          <TrendingUp className="w-4 h-4" />
          Staking Rewards
        </button>
        <button
          onClick={() => setActiveTab('validators')}
          className={`flex items-center gap-2 px-4 py-3 border-b-2 transition ${
            activeTab === 'validators'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-gray-400 hover:text-gray-300'
          }`}
        >
          <Building2 className="w-4 h-4" />
          My Validators
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'rewards' ? (
        <StakingRewards />
      ) : (
        <ValidatorTracking />
      )}
    </div>
  );
}

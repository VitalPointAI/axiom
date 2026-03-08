'use client';

import { useState, useEffect } from 'react';
import { ValidatorTracking } from '@/components/validator-tracking';
import { MultichainStaking } from '@/components/multichain-staking';
import { TrendingUp, Building2, Download, ArrowUpRight, ArrowDownRight, Gift, List } from 'lucide-react';

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

interface StakingTransaction {
  type: 'stake' | 'unstake' | 'reward';
  date: string;
  epoch?: number;
  validator: string;
  wallet: string;
  amount_near: number;
  price_usd?: number;
  value_usd?: number;
  value_cad?: number;
  tx_hash?: string;
}

interface TransactionStats {
  totalRewards: number;
  totalStaked: number;
  totalUnstaked: number;
  rewardCount: number;
  stakeCount: number;
  unstakeCount: number;
}

function StakingTransactions() {
  const [transactions, setTransactions] = useState<StakingTransaction[]>([]);
  const [stats, setStats] = useState<TransactionStats | null>(null);
  const [selectedYear, setSelectedYear] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'stake' | 'unstake' | 'reward'>('all');

  useEffect(() => {
    fetchData();
  }, [selectedYear]);

  const fetchData = async () => {
    setLoading(true);
    const url = selectedYear 
      ? `/api/staking/transactions?year=${selectedYear}` 
      : '/api/staking/transactions';
    const res = await fetch(url);
    const data = await res.json();
    setTransactions(data.transactions || []);
    setStats(data.stats || null);
    setLoading(false);
  };

  const downloadKoinly = () => {
    const url = selectedYear 
      ? `/api/staking/transactions?year=${selectedYear}&format=koinly` 
      : '/api/staking/transactions?format=koinly';
    window.location.href = url;
  };

  const formatNear = (n: number) => n?.toLocaleString(undefined, { 
    minimumFractionDigits: 5,
    maximumFractionDigits: 5 
  }) || '0.00000';
  
  const formatCad = (n: number) => '$' + (n?.toLocaleString(undefined, { 
    minimumFractionDigits: 2,
    maximumFractionDigits: 2 
  }) || '0.00');

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-CA', { 
      year: 'numeric', 
      month: 'short', 
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const years = [2020, 2021, 2022, 2023, 2024, 2025, 2026];

  const filteredTx = filter === 'all' 
    ? transactions 
    : transactions.filter(t => t.type === filter);

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'stake': return <ArrowUpRight className="w-4 h-4 text-green-400" />;
      case 'unstake': return <ArrowDownRight className="w-4 h-4 text-red-400" />;
      case 'reward': return <Gift className="w-4 h-4 text-purple-400" />;
      default: return null;
    }
  };

  const getTypeBadge = (type: string) => {
    switch (type) {
      case 'stake': return 'bg-green-500/20 text-green-400 border-green-500/30';
      case 'unstake': return 'bg-red-500/20 text-red-400 border-red-500/30';
      case 'reward': return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
      default: return 'bg-slate-500/20 text-slate-400';
    }
  };

  return (
    <div className="space-y-6">
      {/* Controls Row */}
      <div className="flex flex-wrap gap-4 items-center justify-between">
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

        {/* Export Button */}
        <button
          onClick={downloadKoinly}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg transition"
        >
          <Download className="w-4 h-4" />
          Export for Koinly
        </button>
      </div>

      {loading ? (
        <div className="text-center py-10 text-gray-400">Loading...</div>
      ) : (
        <>
          {/* Stats Summary */}
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
              <div className="bg-purple-600/20 border border-purple-500/30 rounded-lg p-4">
                <div className="text-2xl font-bold text-purple-400">{formatNear(stats.totalRewards)}</div>
                <div className="text-sm text-gray-400">NEAR Rewards</div>
                <div className="text-xs text-gray-500">{stats.rewardCount} epochs</div>
              </div>
              <div className="bg-green-600/20 border border-green-500/30 rounded-lg p-4">
                <div className="text-2xl font-bold text-green-400">{formatNear(stats.totalStaked)}</div>
                <div className="text-sm text-gray-400">Total Staked</div>
                <div className="text-xs text-gray-500">{stats.stakeCount} transactions</div>
              </div>
              <div className="bg-red-600/20 border border-red-500/30 rounded-lg p-4">
                <div className="text-2xl font-bold text-red-400">{formatNear(stats.totalUnstaked)}</div>
                <div className="text-sm text-gray-400">Total Unstaked</div>
                <div className="text-xs text-gray-500">{stats.unstakeCount} transactions</div>
              </div>
              <div className="col-span-2 md:col-span-3 lg:col-span-3 bg-slate-800 border border-slate-700 rounded-lg p-4">
                <div className="text-lg font-semibold text-white mb-2">Quick Filters</div>
                <div className="flex gap-2 flex-wrap">
                  <button
                    onClick={() => setFilter('all')}
                    className={`px-3 py-1 rounded transition ${filter === 'all' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-gray-300 hover:bg-slate-600'}`}
                  >
                    All ({transactions.length})
                  </button>
                  <button
                    onClick={() => setFilter('reward')}
                    className={`px-3 py-1 rounded transition ${filter === 'reward' ? 'bg-purple-600 text-white' : 'bg-slate-700 text-gray-300 hover:bg-slate-600'}`}
                  >
                    Rewards ({stats.rewardCount})
                  </button>
                  <button
                    onClick={() => setFilter('stake')}
                    className={`px-3 py-1 rounded transition ${filter === 'stake' ? 'bg-green-600 text-white' : 'bg-slate-700 text-gray-300 hover:bg-slate-600'}`}
                  >
                    Stakes ({stats.stakeCount})
                  </button>
                  <button
                    onClick={() => setFilter('unstake')}
                    className={`px-3 py-1 rounded transition ${filter === 'unstake' ? 'bg-red-600 text-white' : 'bg-slate-700 text-gray-300 hover:bg-slate-600'}`}
                  >
                    Unstakes ({stats.unstakeCount})
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Transactions Table */}
          <div className="bg-slate-800 rounded-lg border border-slate-700 overflow-hidden">
            <div className="p-4 border-b border-slate-700 flex justify-between items-center">
              <h2 className="text-xl font-semibold text-white flex items-center gap-2">
                <List className="w-5 h-5" />
                Staking Transactions
              </h2>
              <div className="text-sm text-gray-400">
                {filteredTx.length} transaction{filteredTx.length !== 1 ? 's' : ''}
              </div>
            </div>
            
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-700 bg-slate-800/50">
                    <th className="text-left py-3 px-4 text-gray-400 font-medium">Date</th>
                    <th className="text-left py-3 px-4 text-gray-400 font-medium">Type</th>
                    <th className="text-left py-3 px-4 text-gray-400 font-medium">Epoch</th>
                    <th className="text-left py-3 px-4 text-gray-400 font-medium">Validator</th>
                    <th className="text-left py-3 px-4 text-gray-400 font-medium">Wallet</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">Amount (NEAR)</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">Price (USD)</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">Value (CAD)</th>
                    <th className="text-left py-3 px-4 text-gray-400 font-medium">TX</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTx.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="text-center py-10 text-gray-500">
                        No staking transactions found
                      </td>
                    </tr>
                  ) : (
                    filteredTx.map((tx, i) => (
                      <tr key={i} className="border-b border-slate-700/50 hover:bg-slate-700/30 transition">
                        <td className="py-3 px-4 text-white text-sm">{formatDate(tx.date)}</td>
                        <td className="py-3 px-4">
                          <span className={`inline-flex items-center gap-1 px-2 py-1 rounded border text-xs font-medium ${getTypeBadge(tx.type)}`}>
                            {getTypeIcon(tx.type)}
                            {tx.type.toUpperCase()}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-gray-400 text-sm">
                          {tx.epoch || '-'}
                        </td>
                        <td className="py-3 px-4 font-mono text-sm text-gray-300 max-w-[200px] truncate" title={tx.validator}>
                          {tx.validator}
                        </td>
                        <td className="py-3 px-4 font-mono text-sm text-gray-400 max-w-[150px] truncate" title={tx.wallet}>
                          {tx.wallet}
                        </td>
                        <td className="py-3 px-4 text-right font-mono text-white">
                          {formatNear(tx.amount_near)}
                        </td>
                        <td className="py-3 px-4 text-right text-gray-400 text-sm">
                          {tx.price_usd ? `$${tx.price_usd.toFixed(4)}` : '-'}
                        </td>
                        <td className="py-3 px-4 text-right font-semibold text-white">
                          {tx.value_cad ? formatCad(tx.value_cad) : '-'}
                        </td>
                        <td className="py-3 px-4">
                          {tx.tx_hash ? (
                            <a
                              href={`https://nearblocks.io/txns/${tx.tx_hash}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-400 hover:text-blue-300 text-xs font-mono"
                            >
                              {tx.tx_hash.slice(0, 8)}...
                            </a>
                          ) : (
                            <span className="text-gray-500 text-xs">-</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Tax Note */}
          <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
            <p className="text-sm text-gray-400">
              <strong className="text-gray-300">💰 Tax Note:</strong> Staking rewards are taxable income in Canada 
              at the fair market value when received. Stakes/unstakes are internal transfers and not taxable events.
              Export to Koinly to auto-categorize for your tax return.
            </p>
          </div>
        </>
      )}
    </div>
  );
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
  const [activeTab, setActiveTab] = useState<'transactions' | 'rewards' | 'validators'>('transactions');

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
          onClick={() => setActiveTab('transactions')}
          className={`flex items-center gap-2 px-4 py-3 border-b-2 transition ${
            activeTab === 'transactions'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-gray-400 hover:text-gray-300'
          }`}
        >
          <List className="w-4 h-4" />
          All Transactions
        </button>
        <button
          onClick={() => setActiveTab('rewards')}
          className={`flex items-center gap-2 px-4 py-3 border-b-2 transition ${
            activeTab === 'rewards'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-gray-400 hover:text-gray-300'
          }`}
        >
          <TrendingUp className="w-4 h-4" />
          Rewards Summary
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
      {activeTab === 'transactions' ? (
        <StakingTransactions />
      ) : activeTab === 'rewards' ? (
        <StakingRewards />
      ) : (
        <>
          <ValidatorTracking />
          <MultichainStaking />
        </>
      )}
    </div>
  );
}

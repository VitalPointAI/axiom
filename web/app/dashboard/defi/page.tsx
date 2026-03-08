'use client';

import { useState, useEffect } from 'react';
import { Coins, TrendingUp, RefreshCw, AlertTriangle, Banknote } from 'lucide-react';

interface DefiSummary {
  byCategory: Array<{
    year: string;
    tax_category: string;
    protocol: string;
    count: number;
    total_usd: number;
    total_cad: number;
  }>;
  income: Array<{
    year: string;
    token_symbol: string;
    protocol: string;
    count: number;
    total_tokens: number;
    total_usd: number;
    total_cad: number;
  }>;
  trades: Array<{
    year: string;
    protocol: string;
    count: number;
  }>;
  protocols: Array<{
    protocol: string;
    count: number;
    income_count: number;
    trade_count: number;
  }>;
  needsReview: number;
  missingPrices: number;
}

export default function DefiPage() {
  const [summary, setSummary] = useState<DefiSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedYear, setSelectedYear] = useState<string>('2025');

  useEffect(() => {
    fetchSummary();
  }, []);

  const fetchSummary = async () => {
    try {
      const res = await fetch('/api/defi/summary');
      const data = await res.json();
      setSummary(data);
    } catch (err) {
      console.error('Failed to fetch DeFi summary:', err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-slate-400" />
      </div>
    );
  }

  if (!summary) {
    return <div className="text-red-500">Failed to load DeFi data</div>;
  }

  // Get unique years
  const years = [...new Set(summary.byCategory.map(e => e.year))].sort().reverse();

  // Filter data by selected year
  const yearIncome = summary.income.filter(e => e.year === selectedYear);
  const yearTrades = summary.trades.filter(e => e.year === selectedYear);
  const yearCategories = summary.byCategory.filter(e => e.year === selectedYear);

  // Calculate totals for selected year
  const totalIncome = yearIncome.reduce((sum, e) => sum + (e.total_usd || 0), 0);
  const totalTrades = yearTrades.reduce((sum, e) => sum + e.count, 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">DeFi Activity</h1>
          <p className="text-slate-500">
            Track your DeFi income and trades across protocols
          </p>
        </div>
        <div className="flex items-center gap-4">
          <select
            value={selectedYear}
            onChange={(e) => setSelectedYear(e.target.value)}
            className="px-4 py-2 border rounded-lg bg-white"
          >
            {years.map(year => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-lg shadow-sm border p-6">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-green-50 rounded-lg">
              <Banknote className="w-6 h-6 text-green-600" />
            </div>
            <div>
              <p className="text-sm text-slate-500">Income ({selectedYear})</p>
              <p className="text-2xl font-bold text-slate-900">
                ${totalIncome.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border p-6">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-blue-50 rounded-lg">
              <TrendingUp className="w-6 h-6 text-blue-600" />
            </div>
            <div>
              <p className="text-sm text-slate-500">Trades ({selectedYear})</p>
              <p className="text-2xl font-bold text-slate-900">{totalTrades}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border p-6">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-purple-50 rounded-lg">
              <Coins className="w-6 h-6 text-purple-600" />
            </div>
            <div>
              <p className="text-sm text-slate-500">Protocols</p>
              <p className="text-2xl font-bold text-slate-900">{summary.protocols.length}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow-sm border p-6">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-orange-50 rounded-lg">
              <AlertTriangle className="w-6 h-6 text-orange-600" />
            </div>
            <div>
              <p className="text-sm text-slate-500">Needs Review</p>
              <p className="text-2xl font-bold text-slate-900">{summary.needsReview}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Protocol Summary */}
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <h2 className="text-lg font-semibold text-slate-700 mb-4">Protocol Summary</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {summary.protocols.map(p => (
            <div key={p.protocol} className="border rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <div className={`w-3 h-3 rounded-full ${
                  p.protocol === 'burrow' ? 'bg-blue-500' :
                  p.protocol === 'ref_finance' ? 'bg-green-500' :
                  'bg-purple-500'
                }`} />
                <h3 className="font-semibold capitalize">{p.protocol.replace('_', ' ')}</h3>
              </div>
              <div className="text-sm text-slate-600 space-y-1">
                <p>Total Events: {p.count}</p>
                <p>Income Events: {p.income_count}</p>
                <p>Trades: {p.trade_count}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Income by Token */}
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <h2 className="text-lg font-semibold text-slate-700 mb-4">
          Income by Token ({selectedYear})
        </h2>
        {yearIncome.length > 0 ? (
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2 text-slate-500 font-medium">Token</th>
                <th className="text-left py-2 text-slate-500 font-medium">Protocol</th>
                <th className="text-right py-2 text-slate-500 font-medium">Events</th>
                <th className="text-right py-2 text-slate-500 font-medium">Amount</th>
                <th className="text-right py-2 text-slate-500 font-medium">Value (USD)</th>
              </tr>
            </thead>
            <tbody>
              {yearIncome.map((item, i) => (
                <tr key={i} className="border-b last:border-0">
                  <td className="py-3 font-medium">{item.token_symbol}</td>
                  <td className="py-3 capitalize text-slate-600">
                    {item.protocol.replace('_', ' ')}
                  </td>
                  <td className="py-3 text-right">{item.count}</td>
                  <td className="py-3 text-right">
                    {item.total_tokens.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </td>
                  <td className="py-3 text-right">
                    ${(item.total_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-slate-500 text-center py-8">No income recorded for {selectedYear}</p>
        )}
      </div>

      {/* Activity by Category */}
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <h2 className="text-lg font-semibold text-slate-700 mb-4">
          Activity by Category ({selectedYear})
        </h2>
        {yearCategories.length > 0 ? (
          <table className="w-full">
            <thead>
              <tr className="border-b">
                <th className="text-left py-2 text-slate-500 font-medium">Category</th>
                <th className="text-left py-2 text-slate-500 font-medium">Protocol</th>
                <th className="text-right py-2 text-slate-500 font-medium">Events</th>
                <th className="text-right py-2 text-slate-500 font-medium">Value (USD)</th>
              </tr>
            </thead>
            <tbody>
              {yearCategories.map((item, i) => (
                <tr key={i} className="border-b last:border-0">
                  <td className="py-3">
                    <span className={`px-2 py-1 rounded text-sm ${
                      item.tax_category === 'income' ? 'bg-green-100 text-green-700' :
                      item.tax_category === 'trade' ? 'bg-blue-100 text-blue-700' :
                      item.tax_category === 'stake' ? 'bg-purple-100 text-purple-700' :
                      item.tax_category === 'unstake' ? 'bg-orange-100 text-orange-700' :
                      'bg-slate-100 text-slate-700'
                    }`}>
                      {item.tax_category}
                    </span>
                  </td>
                  <td className="py-3 capitalize text-slate-600">
                    {item.protocol.replace('_', ' ')}
                  </td>
                  <td className="py-3 text-right">{item.count}</td>
                  <td className="py-3 text-right">
                    ${(item.total_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-slate-500 text-center py-8">No activity for {selectedYear}</p>
        )}
      </div>
    </div>
  );
}

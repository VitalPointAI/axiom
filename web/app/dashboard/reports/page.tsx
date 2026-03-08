'use client';

import { useState, useEffect } from 'react';
import { FileText, Download, AlertTriangle, CheckCircle, DollarSign, Globe, TrendingUp, RefreshCw } from 'lucide-react';

interface ReportSummary {
  year: string;
  categories: Array<{ tax_category: string; count: number; total_cad: number }>;
  stakingRewards: number;
  defiIncome: Array<{ token_symbol: string; total_tokens: number; total_cad: number }>;
  trades: number;
  disposals: Array<{ month: string; count: number; proceeds_cad: number }>;
  warnings: number;
}

interface T1135Report {
  year: string;
  filingRequired: boolean;
  category: string;
  totalMaxCostAmount: number;
  totalYearEndCost: number;
  totalIncome: number;
  foreignProperty: Array<{
    description: string;
    country: string;
    maxCostAmount: number;
    yearEndCostAmount: number;
    income: number;
  }>;
  notes: string[];
}

interface Schedule3Report {
  year: string;
  summary: {
    totalDisposals: number;
    totalProceeds: number;
    totalACB: number;
    totalGainLoss: number;
    taxableCapitalGain: number;
    allowableCapitalLoss: number;
  };
  disposals: Array<{
    date: string;
    description: string;
    proceeds: number;
    acb: number;
    gainLoss: number;
  }>;
  notes: string[];
}

export default function ReportsPage() {
  const [year, setYear] = useState('2025');
  const [loading, setLoading] = useState(true);
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  const [t1135, setT1135] = useState<T1135Report | null>(null);
  const [schedule3, setSchedule3] = useState<Schedule3Report | null>(null);
  const [activeTab, setActiveTab] = useState<'summary' | 't1135' | 'schedule3'>('summary');

  useEffect(() => {
    fetchReports();
  }, [year]);

  const fetchReports = async () => {
    setLoading(true);
    try {
      const [sumRes, t1135Res, s3Res] = await Promise.all([
        fetch(`/api/reports/summary?year=${year}`),
        fetch(`/api/reports/t1135?year=${year}`),
        fetch(`/api/reports/schedule3?year=${year}`)
      ]);
      
      setSummary(await sumRes.json());
      setT1135(await t1135Res.json());
      setSchedule3(await s3Res.json());
    } catch (err) {
      console.error('Failed to fetch reports:', err);
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Tax Reports</h1>
          <p className="text-slate-500">
            Canadian tax forms for cryptocurrency holdings
          </p>
        </div>
        <div className="flex items-center gap-4">
          <select
            value={year}
            onChange={(e) => setYear(e.target.value)}
            className="px-4 py-2 border rounded-lg bg-white"
          >
            <option value="2025">2025</option>
            <option value="2024">2024</option>
            <option value="2023">2023</option>
            <option value="2022">2022</option>
          </select>
          <div className="flex gap-2">
            <a
              href={`/api/reports/export?year=${year}&report=schedule3&format=csv`}
              className="flex items-center gap-2 px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition text-sm"
            >
              <Download className="w-4 h-4" />
              Schedule 3 CSV
            </a>
            <a
              href={`/api/reports/export?year=${year}&report=t1135&format=csv`}
              className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition text-sm"
            >
              <Download className="w-4 h-4" />
              T1135 CSV
            </a>
            <a
              href={`/api/reports/export?year=${year}&report=transactions&format=csv`}
              className="flex items-center gap-2 px-3 py-2 bg-slate-600 text-white rounded-lg hover:bg-slate-700 transition text-sm"
            >
              <Download className="w-4 h-4" />
              All Transactions
            </a>
          </div>
        </div>
      </div>

      {/* Warnings */}
      {summary && summary.warnings > 0 && (
        <div className="bg-orange-50 border border-orange-200 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-orange-500 flex-shrink-0" />
          <div>
            <p className="font-medium text-orange-800">
              {summary.warnings} transactions need price review
            </p>
            <p className="text-sm text-orange-600">
              Resolve price warnings for accurate tax calculations
            </p>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b">
        <div className="flex gap-4">
          {(['summary', 't1135', 'schedule3'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-3 border-b-2 transition ${
                activeTab === tab
                  ? 'border-blue-500 text-blue-600 font-medium'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              {tab === 'summary' && 'Summary'}
              {tab === 't1135' && 'T1135 Foreign Property'}
              {tab === 'schedule3' && 'Schedule 3 Capital Gains'}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'summary' && summary && (
        <div className="space-y-6">
          {/* Key Stats */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <div className="flex items-center gap-3">
                <div className="p-3 bg-green-50 rounded-lg">
                  <DollarSign className="w-6 h-6 text-green-600" />
                </div>
                <div>
                  <p className="text-sm text-slate-500">Staking Rewards</p>
                  <p className="text-xl font-bold text-slate-900">
                    {summary.stakingRewards.toLocaleString(undefined, { maximumFractionDigits: 2 })} NEAR
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
                  <p className="text-sm text-slate-500">DeFi Trades</p>
                  <p className="text-xl font-bold text-slate-900">{summary.trades}</p>
                </div>
              </div>
            </div>
            
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <div className="flex items-center gap-3">
                <div className="p-3 bg-purple-50 rounded-lg">
                  <FileText className="w-6 h-6 text-purple-600" />
                </div>
                <div>
                  <p className="text-sm text-slate-500">Disposals</p>
                  <p className="text-xl font-bold text-slate-900">
                    {summary.disposals.reduce((sum, d) => sum + d.count, 0)}
                  </p>
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
                  <p className="text-xl font-bold text-slate-900">{summary.warnings}</p>
                </div>
              </div>
            </div>
          </div>

          {/* DeFi Income */}
          {summary.defiIncome.length > 0 && (
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <h2 className="text-lg font-semibold text-slate-700 mb-4">DeFi Income</h2>
              <table className="w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 text-slate-500 font-medium">Token</th>
                    <th className="text-right py-2 text-slate-500 font-medium">Amount</th>
                    <th className="text-right py-2 text-slate-500 font-medium">Value (CAD)</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.defiIncome.map((item, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-3 font-medium">{item.token_symbol}</td>
                      <td className="py-3 text-right">
                        {item.total_tokens.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </td>
                      <td className="py-3 text-right">
                        ${item.total_cad.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Monthly Disposals */}
          {summary.disposals.length > 0 && (
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <h2 className="text-lg font-semibold text-slate-700 mb-4">Monthly Disposals</h2>
              <table className="w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 text-slate-500 font-medium">Month</th>
                    <th className="text-right py-2 text-slate-500 font-medium">Count</th>
                    <th className="text-right py-2 text-slate-500 font-medium">Proceeds (CAD)</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.disposals.map((item, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-3">{item.month}</td>
                      <td className="py-3 text-right">{item.count}</td>
                      <td className="py-3 text-right">
                        ${item.proceeds_cad.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 't1135' && t1135 && (
        <div className="space-y-6">
          {/* Filing Status */}
          <div className={`rounded-lg p-6 ${
            t1135.filingRequired ? 'bg-orange-50 border border-orange-200' : 'bg-green-50 border border-green-200'
          }`}>
            <div className="flex items-center gap-3">
              {t1135.filingRequired ? (
                <AlertTriangle className="w-6 h-6 text-orange-500" />
              ) : (
                <CheckCircle className="w-6 h-6 text-green-500" />
              )}
              <div>
                <p className="font-semibold text-lg">
                  {t1135.filingRequired ? 'T1135 Filing Required' : 'T1135 Filing Not Required'}
                </p>
                <p className={t1135.filingRequired ? 'text-orange-700' : 'text-green-700'}>
                  {t1135.category}
                </p>
              </div>
            </div>
          </div>

          {/* Summary Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <p className="text-sm text-slate-500">Maximum Cost Amount</p>
              <p className="text-2xl font-bold text-slate-900">
                ${t1135.totalMaxCostAmount.toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD
              </p>
            </div>
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <p className="text-sm text-slate-500">Year-End Cost Amount</p>
              <p className="text-2xl font-bold text-slate-900">
                ${t1135.totalYearEndCost.toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD
              </p>
            </div>
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <p className="text-sm text-slate-500">Foreign Income</p>
              <p className="text-2xl font-bold text-slate-900">
                ${t1135.totalIncome.toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD
              </p>
            </div>
          </div>

          {/* Foreign Property Details */}
          <div className="bg-white rounded-lg shadow-sm border p-6">
            <h2 className="text-lg font-semibold text-slate-700 mb-4">Specified Foreign Property</h2>
            <table className="w-full">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 text-slate-500 font-medium">Description</th>
                  <th className="text-left py-2 text-slate-500 font-medium">Country</th>
                  <th className="text-right py-2 text-slate-500 font-medium">Max Cost</th>
                  <th className="text-right py-2 text-slate-500 font-medium">Year-End</th>
                  <th className="text-right py-2 text-slate-500 font-medium">Income</th>
                </tr>
              </thead>
              <tbody>
                {t1135.foreignProperty.map((item, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="py-3">{item.description}</td>
                    <td className="py-3">{item.country}</td>
                    <td className="py-3 text-right">
                      ${item.maxCostAmount.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                    <td className="py-3 text-right">
                      ${item.yearEndCostAmount.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                    <td className="py-3 text-right">
                      ${item.income.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Notes */}
          <div className="bg-slate-50 rounded-lg p-6">
            <h3 className="font-medium text-slate-700 mb-2">Important Notes</h3>
            <ul className="list-disc list-inside space-y-1 text-sm text-slate-600">
              {t1135.notes.map((note, i) => (
                <li key={i}>{note}</li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {activeTab === 'schedule3' && schedule3 && (
        <div className="space-y-6">
          {/* Summary */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <p className="text-sm text-slate-500">Total Proceeds</p>
              <p className="text-2xl font-bold text-slate-900">
                ${schedule3.summary.totalProceeds.toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD
              </p>
            </div>
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <p className="text-sm text-slate-500">Adjusted Cost Base</p>
              <p className="text-2xl font-bold text-slate-900">
                ${schedule3.summary.totalACB.toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD
              </p>
            </div>
            <div className={`rounded-lg shadow-sm border p-6 ${
              schedule3.summary.totalGainLoss >= 0 ? 'bg-green-50' : 'bg-red-50'
            }`}>
              <p className="text-sm text-slate-500">
                {schedule3.summary.totalGainLoss >= 0 ? 'Capital Gain' : 'Capital Loss'}
              </p>
              <p className={`text-2xl font-bold ${
                schedule3.summary.totalGainLoss >= 0 ? 'text-green-700' : 'text-red-700'
              }`}>
                ${Math.abs(schedule3.summary.totalGainLoss).toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD
              </p>
            </div>
          </div>

          {/* Taxable Amount */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-blue-700">
                  {schedule3.summary.taxableCapitalGain > 0 
                    ? 'Taxable Capital Gain (50% inclusion)'
                    : 'Allowable Capital Loss (50% inclusion)'
                  }
                </p>
                <p className="text-3xl font-bold text-blue-900">
                  ${(schedule3.summary.taxableCapitalGain || schedule3.summary.allowableCapitalLoss).toLocaleString(undefined, { maximumFractionDigits: 0 })} CAD
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm text-blue-600">{schedule3.summary.totalDisposals} disposals</p>
              </div>
            </div>
          </div>

          {/* Disposals Table */}
          <div className="bg-white rounded-lg shadow-sm border p-6">
            <h2 className="text-lg font-semibold text-slate-700 mb-4">Disposals</h2>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b">
                    <th className="text-left py-2 text-slate-500 font-medium">Date</th>
                    <th className="text-left py-2 text-slate-500 font-medium">Description</th>
                    <th className="text-right py-2 text-slate-500 font-medium">Proceeds</th>
                    <th className="text-right py-2 text-slate-500 font-medium">ACB</th>
                    <th className="text-right py-2 text-slate-500 font-medium">Gain/Loss</th>
                  </tr>
                </thead>
                <tbody>
                  {schedule3.disposals.map((item, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-3 text-sm">{item.date}</td>
                      <td className="py-3 text-sm">{item.description}</td>
                      <td className="py-3 text-right">
                        ${item.proceeds.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </td>
                      <td className="py-3 text-right">
                        ${item.acb.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </td>
                      <td className={`py-3 text-right ${
                        item.gainLoss >= 0 ? 'text-green-600' : 'text-red-600'
                      }`}>
                        ${item.gainLoss.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Notes */}
          <div className="bg-slate-50 rounded-lg p-6">
            <h3 className="font-medium text-slate-700 mb-2">Important Notes</h3>
            <ul className="list-disc list-inside space-y-1 text-sm text-slate-600">
              {schedule3.notes.map((note, i) => (
                <li key={i}>{note}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

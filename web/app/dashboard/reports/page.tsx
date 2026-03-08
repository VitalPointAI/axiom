'use client';

import { useState, useEffect } from 'react';
import StakingRewardsTable from '@/components/staking-rewards-table';
import { FileText, Download, TrendingUp, TrendingDown, Gift, DollarSign, Wallet, BarChart3, Coins, 
         RefreshCw, Globe, Landmark, AlertTriangle, CheckCircle, ArrowUpRight, ArrowDownLeft,
         Calendar, PiggyBank, Receipt, Scale, BookOpen } from 'lucide-react';

type ReportTab = 'summary' | 'schedule3' | 't1135' | 'income' | 'capital-gains' | 'other-gains' | 'staking-rewards' | 
                 'gifts' | 'expenses' | 'holdings-start' | 'holdings-end' | 'highest-balance' | 
                 'buy-sell' | 'ledger' | 'wallet-balances' | 'transactions';

interface TabConfig {
  id: ReportTab;
  label: string;
  icon: typeof FileText;
  description: string;
}

const tabs: TabConfig[] = [
  { id: 'summary', label: 'Summary', icon: FileText, description: 'Tax year overview' },
  { id: 'schedule3', label: 'Schedule 3', icon: Scale, description: 'Capital gains (CRA)' },
  { id: 't1135', label: 'T1135', icon: Globe, description: 'Foreign property' },
  { id: 'capital-gains', label: 'Capital Gains', icon: TrendingUp, description: 'Detailed gains/losses' },
  { id: 'income', label: 'Income', icon: DollarSign, description: 'All income sources' },
  { id: 'other-gains', label: 'Other Gains', icon: PiggyBank, description: 'Airdrops, staking, mining' },
  { id: 'staking-rewards', label: 'Staking Rewards', icon: Coins, description: 'Per-epoch NEAR staking' },
  { id: 'gifts', label: 'Gifts & Lost', icon: Gift, description: 'Gifts, donations, lost assets' },
  { id: 'expenses', label: 'Expenses', icon: Receipt, description: 'Fees and costs' },
  { id: 'holdings-start', label: 'Holdings (Jan 1)', icon: Calendar, description: 'Beginning of year' },
  { id: 'holdings-end', label: 'Holdings (Dec 31)', icon: Calendar, description: 'End of year' },
  { id: 'highest-balance', label: 'Highest Balance', icon: BarChart3, description: 'Peak portfolio value' },
  { id: 'buy-sell', label: 'Buy/Sell', icon: ArrowUpRight, description: 'All acquisitions & disposals' },
  { id: 'ledger', label: 'Ledger', icon: BookOpen, description: 'Running balance' },
  { id: 'wallet-balances', label: 'Per Wallet', icon: Wallet, description: 'Balances by wallet' },
  { id: 'transactions', label: 'All Transactions', icon: FileText, description: 'Complete history' },
];

export default function ReportsPage() {
  const [year, setYear] = useState('2025');
  const [activeTab, setActiveTab] = useState<ReportTab>('summary');
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);
  const [ledgerToken, setLedgerToken] = useState('NEAR');

  useEffect(() => {
    fetchReport();
  }, [year, activeTab, ledgerToken]);

  const fetchReport = async () => {
    setLoading(true);
    try {
      let url = '';
      switch (activeTab) {
        case 'summary': url = `/api/reports/summary?year=${year}`; break;
        case 'schedule3': url = `/api/reports/schedule3?year=${year}`; break;
        case 't1135': url = `/api/reports/t1135?year=${year}`; break;
        case 'income': url = `/api/reports/income?year=${year}`; break;
        case 'capital-gains': url = `/api/reports/schedule3?year=${year}`; break;
        case 'other-gains': url = `/api/reports/other-gains?year=${year}`; break;
        case 'staking-rewards': url = ''; break; // Uses component's own fetch
        case 'gifts': url = `/api/reports/gifts-donations?year=${year}`; break;
        case 'expenses': url = `/api/reports/expenses?year=${year}`; break;
        case 'holdings-start': url = `/api/reports/holdings?year=${year}&period=start`; break;
        case 'holdings-end': url = `/api/reports/holdings?year=${year}&period=end`; break;
        case 'highest-balance': url = `/api/reports/highest-balance?year=${year}`; break;
        case 'buy-sell': url = `/api/reports/buy-sell?year=${year}`; break;
        case 'ledger': url = `/api/reports/ledger?year=${year}&token=${ledgerToken}`; break;
        case 'wallet-balances': url = `/api/reports/wallet-balances?year=${year}`; break;
        case 'transactions': url = `/api/reports/transactions?year=${year}`; break;
      }
      const res = await fetch(url);
      setData(await res.json());
    } catch (err) {
      console.error('Failed to fetch report:', err);
    } finally {
      setLoading(false);
    }
  };

  const downloadCsv = async () => {
    let url = '';
    switch (activeTab) {
      case 'schedule3':
      case 'capital-gains': url = `/api/reports/schedule3?year=${year}&format=csv`; break;
      case 'other-gains': url = `/api/reports/other-gains?year=${year}&format=csv`; break;
      case 'staking-rewards': url = `/api/staking/rewards?year=${year}&format=csv`; break;
      case 'gifts': url = `/api/reports/gifts-donations?year=${year}&format=csv`; break;
      case 'expenses': url = `/api/reports/expenses?year=${year}&format=csv`; break;
      case 'holdings-start': url = `/api/reports/holdings?year=${year}&period=start&format=csv`; break;
      case 'holdings-end': url = `/api/reports/holdings?year=${year}&period=end&format=csv`; break;
      case 'highest-balance': url = `/api/reports/highest-balance?year=${year}&format=csv`; break;
      case 'buy-sell': url = `/api/reports/buy-sell?year=${year}&format=csv`; break;
      case 'ledger': url = `/api/reports/ledger?year=${year}&token=${ledgerToken}&format=csv`; break;
      case 'wallet-balances': url = `/api/reports/wallet-balances?year=${year}&format=csv`; break;
      case 'transactions': url = `/api/reports/transactions?year=${year}&format=csv`; break;
      default: url = `/api/reports/export?year=${year}&report=${activeTab}`; break;
    }
    window.open(url, '_blank');
  };

  const formatCad = (n: number) => '$' + (n || 0).toLocaleString(undefined, { maximumFractionDigits: 2 });
  const formatAmount = (n: number) => (n || 0).toLocaleString(undefined, { maximumFractionDigits: 8 });

  const renderContent = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center h-64">
          <RefreshCw className="w-8 h-8 animate-spin text-slate-400" />
        </div>
      );
    }

    if (!data) {
      return <div className="text-center text-slate-500 py-8">No data available</div>;
    }

    switch (activeTab) {
      case 'summary':
        return (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-blue-50 rounded-lg p-4">
                <div className="text-sm text-blue-600 font-medium">Capital Gains</div>
                <div className="text-2xl font-bold text-blue-900">{formatCad(data.capitalGains?.netGainLoss || 0)}</div>
                <div className="text-xs text-blue-500">{data.capitalGains?.disposals || 0} disposals</div>
              </div>
              <div className="bg-green-50 rounded-lg p-4">
                <div className="text-sm text-green-600 font-medium">Staking Income</div>
                <div className="text-2xl font-bold text-green-900">{formatCad(data.stakingIncome?.cad || 0)}</div>
                <div className="text-xs text-green-500">{formatAmount(data.stakingIncome?.near || 0)} NEAR</div>
              </div>
              <div className="bg-purple-50 rounded-lg p-4">
                <div className="text-sm text-purple-600 font-medium">Price Warnings</div>
                <div className="text-2xl font-bold text-purple-900">{data.warnings || 0}</div>
                <div className="text-xs text-purple-500">Missing prices</div>
              </div>
            </div>
            {data.categories && data.categories.length > 0 && (
              <div>
                <h3 className="font-semibold mb-2">Transaction Categories</h3>
                <div className="bg-white border rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50">
                      <tr>
                        <th className="text-left px-4 py-2">Category</th>
                        <th className="text-right px-4 py-2">Count</th>
                        <th className="text-right px-4 py-2">Total (CAD)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.categories.map((c: any, i: number) => (
                        <tr key={i} className="border-t">
                          <td className="px-4 py-2">{c.tax_category || 'Uncategorized'}</td>
                          <td className="text-right px-4 py-2">{c.count}</td>
                          <td className="text-right px-4 py-2">{formatCad(c.total_cad)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        );

      case 'schedule3':
      case 'capital-gains':
        return (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-sm text-slate-600">Total Proceeds</div>
                <div className="text-xl font-bold">{formatCad(data.summary?.totalProceeds)}</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-sm text-slate-600">Total ACB</div>
                <div className="text-xl font-bold">{formatCad(data.summary?.totalACB)}</div>
              </div>
              <div className={`rounded-lg p-4 ${data.summary?.totalGainLoss >= 0 ? 'bg-green-50' : 'bg-red-50'}`}>
                <div className={`text-sm ${data.summary?.totalGainLoss >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  Net Gain/Loss
                </div>
                <div className={`text-xl font-bold ${data.summary?.totalGainLoss >= 0 ? 'text-green-900' : 'text-red-900'}`}>
                  {formatCad(data.summary?.totalGainLoss)}
                </div>
              </div>
              <div className="bg-blue-50 rounded-lg p-4">
                <div className="text-sm text-blue-600">Taxable (50%)</div>
                <div className="text-xl font-bold text-blue-900">
                  {formatCad(data.summary?.taxableCapitalGain || data.summary?.allowableCapitalLoss)}
                </div>
              </div>
            </div>
            {data.disposals && data.disposals.length > 0 && (
              <div className="bg-white border rounded-lg overflow-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="text-left px-4 py-2">Date</th>
                      <th className="text-left px-4 py-2">Description</th>
                      <th className="text-right px-4 py-2">Proceeds</th>
                      <th className="text-right px-4 py-2">ACB</th>
                      <th className="text-right px-4 py-2">Gain/Loss</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.disposals.slice(0, 50).map((d: any, i: number) => (
                      <tr key={i} className="border-t">
                        <td className="px-4 py-2">{d.date}</td>
                        <td className="px-4 py-2">{d.description}</td>
                        <td className="text-right px-4 py-2">{formatCad(d.proceeds)}</td>
                        <td className="text-right px-4 py-2">{formatCad(d.acb)}</td>
                        <td className={`text-right px-4 py-2 ${d.gainLoss >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                          {formatCad(d.gainLoss)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {data.disposals.length > 50 && (
                  <div className="text-center py-2 text-sm text-slate-500">
                    Showing 50 of {data.disposals.length} disposals. Download CSV for full list.
                  </div>
                )}
              </div>
            )}
          </div>
        );

      case 'other-gains':
        return (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {Object.entries(data.totals || {}).filter(([k]) => k !== 'total').map(([key, val]) => (
                <div key={key} className="bg-slate-50 rounded-lg p-4">
                  <div className="text-sm text-slate-600 capitalize">{key}</div>
                  <div className="text-xl font-bold">{formatCad(val as number)}</div>
                </div>
              ))}
            </div>
            <div className="bg-green-50 rounded-lg p-4 inline-block">
              <div className="text-sm text-green-600">Total Other Income</div>
              <div className="text-2xl font-bold text-green-900">{formatCad(data.totals?.total)}</div>
            </div>
            {['staking', 'airdrops', 'mining', 'forks', 'other'].map(type => {
              const items = data[type];
              if (!items || items.length === 0) return null;
              return (
                <div key={type}>
                  <h3 className="font-semibold mb-2 capitalize">{type} ({items.length})</h3>
                  <div className="bg-white border rounded-lg overflow-auto max-h-64">
                    <table className="w-full text-sm">
                      <thead className="bg-slate-50 sticky top-0">
                        <tr>
                          <th className="text-left px-4 py-2">Date</th>
                          <th className="text-left px-4 py-2">Token</th>
                          <th className="text-right px-4 py-2">Amount</th>
                          <th className="text-right px-4 py-2">Value (CAD)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {items.slice(0, 20).map((item: any, i: number) => (
                          <tr key={i} className="border-t">
                            <td className="px-4 py-2">{item.date}</td>
                            <td className="px-4 py-2">{item.token_symbol}</td>
                            <td className="text-right px-4 py-2">{formatAmount(item.amount)}</td>
                            <td className="text-right px-4 py-2">{formatCad(item.value_cad)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })}
          </div>
        );


      case 'staking-rewards':
        return <StakingRewardsTable year={year} showDownload={true} />;

      case 'holdings-start':
      case 'holdings-end':
        return (
          <div className="space-y-6">
            <div className="bg-blue-50 rounded-lg p-4 inline-block">
              <div className="text-sm text-blue-600">Total Value as of {data.date}</div>
              <div className="text-2xl font-bold text-blue-900">{formatCad(data.totalValueCad)}</div>
            </div>
            {data.holdings && data.holdings.length > 0 && (
              <div className="bg-white border rounded-lg overflow-auto">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="text-left px-4 py-2">Token</th>
                      <th className="text-left px-4 py-2">Chain</th>
                      <th className="text-right px-4 py-2">Balance</th>
                      <th className="text-right px-4 py-2">Price (CAD)</th>
                      <th className="text-right px-4 py-2">Value (CAD)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.holdings.map((h: any, i: number) => (
                      <tr key={i} className="border-t">
                        <td className="px-4 py-2 font-medium">{h.token}</td>
                        <td className="px-4 py-2">{h.chain}</td>
                        <td className="text-right px-4 py-2">{formatAmount(h.balance)}</td>
                        <td className="text-right px-4 py-2">{formatCad(h.priceCad)}</td>
                        <td className="text-right px-4 py-2 font-medium">{formatCad(h.valueCad)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );

      case 'highest-balance':
        return (
          <div className="space-y-6">
            <div className="bg-amber-50 rounded-lg p-6">
              <div className="text-sm text-amber-600">Highest Portfolio Value in {year}</div>
              <div className="text-3xl font-bold text-amber-900">{formatCad(data.highestValueCad)}</div>
              <div className="text-sm text-amber-600 mt-1">on {data.highestValueDate}</div>
            </div>
            {data.monthlyPeaks && data.monthlyPeaks.length > 0 && (
              <div>
                <h3 className="font-semibold mb-2">Monthly Peak Values</h3>
                <div className="bg-white border rounded-lg overflow-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50">
                      <tr>
                        <th className="text-left px-4 py-2">Month</th>
                        <th className="text-left px-4 py-2">Peak Date</th>
                        <th className="text-right px-4 py-2">Value (CAD)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.monthlyPeaks.map((m: any, i: number) => (
                        <tr key={i} className="border-t">
                          <td className="px-4 py-2">{m.month}</td>
                          <td className="px-4 py-2">{m.highestDate}</td>
                          <td className="text-right px-4 py-2 font-medium">{formatCad(m.valueCad)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        );

      case 'ledger':
        return (
          <div className="space-y-4">
            <div className="flex items-center gap-4">
              <label className="text-sm font-medium">Token:</label>
              <select 
                value={ledgerToken} 
                onChange={(e) => setLedgerToken(e.target.value)}
                className="border rounded px-3 py-1"
              >
                <option value="NEAR">NEAR</option>
                <option value="ETH">ETH</option>
                <option value="USDC">USDC</option>
                <option value="USDT">USDT</option>
              </select>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-sm text-slate-600">Opening Balance</div>
                <div className="text-xl font-bold">{formatAmount(data.openingBalance)}</div>
              </div>
              <div className="bg-green-50 rounded-lg p-4">
                <div className="text-sm text-green-600">Total Credits</div>
                <div className="text-xl font-bold text-green-900">+{formatAmount(data.totalCredits)}</div>
              </div>
              <div className="bg-red-50 rounded-lg p-4">
                <div className="text-sm text-red-600">Total Debits</div>
                <div className="text-xl font-bold text-red-900">-{formatAmount(data.totalDebits)}</div>
              </div>
              <div className="bg-blue-50 rounded-lg p-4">
                <div className="text-sm text-blue-600">Closing Balance</div>
                <div className="text-xl font-bold text-blue-900">{formatAmount(data.closingBalance)}</div>
              </div>
            </div>
            {data.entries && data.entries.length > 0 && (
              <div className="bg-white border rounded-lg overflow-auto max-h-96">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 sticky top-0">
                    <tr>
                      <th className="text-left px-4 py-2">Date</th>
                      <th className="text-left px-4 py-2">Description</th>
                      <th className="text-right px-4 py-2 text-red-600">Debit</th>
                      <th className="text-right px-4 py-2 text-green-600">Credit</th>
                      <th className="text-right px-4 py-2">Balance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.entries.map((e: any, i: number) => (
                      <tr key={i} className="border-t">
                        <td className="px-4 py-2">{e.date}</td>
                        <td className="px-4 py-2">{e.description}</td>
                        <td className="text-right px-4 py-2 text-red-600">{e.debit ? formatAmount(e.debit) : ''}</td>
                        <td className="text-right px-4 py-2 text-green-600">{e.credit ? formatAmount(e.credit) : ''}</td>
                        <td className="text-right px-4 py-2 font-medium">{formatAmount(e.balance)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        );

      case 'wallet-balances':
        return (
          <div className="space-y-6">
            <div className="bg-blue-50 rounded-lg p-4 inline-block">
              <div className="text-sm text-blue-600">Total Value (Dec 31, {year})</div>
              <div className="text-2xl font-bold text-blue-900">{formatCad(data.totalValueCad)}</div>
            </div>
            {data.wallets && data.wallets.map((w: any, i: number) => (
              <div key={i} className="bg-white border rounded-lg p-4">
                <div className="flex justify-between items-center mb-3">
                  <div>
                    <div className="font-medium">{w.label || w.address.slice(0, 20) + '...'}</div>
                    <div className="text-xs text-slate-500">{w.chain} • {w.address}</div>
                  </div>
                  <div className="text-right">
                    <div className="font-bold text-lg">{formatCad(w.totalValueCad)}</div>
                  </div>
                </div>
                {w.tokens && w.tokens.length > 0 && (
                  <table className="w-full text-sm">
                    <tbody>
                      {w.tokens.map((t: any, j: number) => (
                        <tr key={j} className="border-t">
                          <td className="py-1">{t.token}</td>
                          <td className="text-right py-1">{formatAmount(t.balance)}</td>
                          <td className="text-right py-1 text-slate-500">{formatCad(t.valueCad)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            ))}
          </div>
        );

      case 'transactions':
        return (
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <div className="text-sm text-slate-500">{data.count} transactions in {year}</div>
            </div>
            {data.transactions && data.transactions.length > 0 && (
              <div className="bg-white border rounded-lg overflow-auto max-h-[600px]">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 sticky top-0">
                    <tr>
                      <th className="text-left px-4 py-2">Date</th>
                      <th className="text-left px-4 py-2">Type</th>
                      <th className="text-left px-4 py-2">Token</th>
                      <th className="text-right px-4 py-2">Amount</th>
                      <th className="text-left px-4 py-2">Category</th>
                      <th className="text-right px-4 py-2">Value (CAD)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.transactions.slice(0, 100).map((t: any, i: number) => (
                      <tr key={i} className="border-t">
                        <td className="px-4 py-2">{t.date?.split(' ')[0]}</td>
                        <td className="px-4 py-2">
                          {t.type === 'Receive' 
                            ? <span className="text-green-600 flex items-center"><ArrowDownLeft className="w-3 h-3 mr-1" />In</span>
                            : <span className="text-red-600 flex items-center"><ArrowUpRight className="w-3 h-3 mr-1" />Out</span>
                          }
                        </td>
                        <td className="px-4 py-2">{t.token}</td>
                        <td className="text-right px-4 py-2">{formatAmount(t.amount)}</td>
                        <td className="px-4 py-2">{t.category || '-'}</td>
                        <td className="text-right px-4 py-2">{formatCad(t.costBasisCad)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {data.transactions.length > 100 && (
                  <div className="text-center py-2 text-sm text-slate-500">
                    Showing 100 of {data.transactions.length}. Download CSV for full list.
                  </div>
                )}
              </div>
            )}
          </div>
        );

      case 't1135':
        return (
          <div className="space-y-6">
            <div className={`rounded-lg p-6 ${data.filingRequired ? 'bg-amber-50 border-2 border-amber-300' : 'bg-green-50'}`}>
              <div className="flex items-center gap-3">
                <Globe className={`w-6 h-6 ${data.filingRequired ? 'text-amber-600' : 'text-green-600'}`} />
                <div>
                  <div className="font-bold text-lg dark:text-white">{data.filingRequired ? 'T1135 Filing Required' : 'T1135 Not Required'}</div>
                  <div className="text-sm text-slate-600 dark:text-slate-300">{data.category}</div>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-blue-50 rounded-lg p-4">
                <div className="text-sm text-blue-600">Max Cost (Year)</div>
                <div className="text-xl font-bold text-blue-900">{formatCad(data.totalMaxCostAmount)}</div>
              </div>
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-sm text-slate-600">Year-End Value</div>
                <div className="text-xl font-bold">{formatCad(data.totalYearEndCost)}</div>
              </div>
              <div className="bg-green-50 rounded-lg p-4">
                <div className="text-sm text-green-600">Foreign Income</div>
                <div className="text-xl font-bold text-green-900">{formatCad(data.totalIncome)}</div>
              </div>
              <div className={`rounded-lg p-4 ${data.totalGainLoss >= 0 ? 'bg-emerald-50' : 'bg-red-50'}`}>
                <div className={`text-sm ${data.totalGainLoss >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>Capital Gain/Loss</div>
                <div className={`text-xl font-bold ${data.totalGainLoss >= 0 ? 'text-emerald-900' : 'text-red-900'}`}>{formatCad(data.totalGainLoss)}</div>
              </div>
            </div>
            {data.foreignProperty && data.foreignProperty.length > 0 && (
              <div className="bg-white border rounded-lg overflow-auto dark:bg-slate-800 dark:border-slate-600">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 dark:bg-slate-700">
                    <tr>
                      <th className="text-left px-4 py-2">Description</th>
                      <th className="text-left px-4 py-2">Country</th>
                      <th className="text-right px-4 py-2">Max Cost</th>
                      <th className="text-right px-4 py-2">Year-End</th>
                      <th className="text-right px-4 py-2">Income</th>
                      <th className="text-right px-4 py-2">Gain/Loss</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.foreignProperty.map((p: any, i: number) => (
                      <tr key={i} className="border-t dark:border-slate-600">
                        <td className="px-4 py-2">{p.description}</td>
                        <td className="px-4 py-2">{p.country}</td>
                        <td className="text-right px-4 py-2">{formatCad(p.maxCostAmount)}</td>
                        <td className="text-right px-4 py-2">{formatCad(p.yearEndCostAmount)}</td>
                        <td className="text-right px-4 py-2">{formatCad(p.income)}</td>
                        <td className={`text-right px-4 py-2 ${p.gainLoss >= 0 ? 'text-green-600' : 'text-red-600'}`}>{formatCad(p.gainLoss)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {data.notes && (
              <div className="text-sm text-slate-500 dark:text-slate-400 space-y-1">
                {data.notes.map((note: string, i: number) => (<div key={i}>• {note}</div>))}
              </div>
            )}
          </div>
        );

      case 'income':
        return (
          <div className="space-y-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-green-50 rounded-lg p-4">
                <div className="text-sm text-green-600">Total Income</div>
                <div className="text-xl font-bold text-green-900">{formatCad(data.income?.total?.cad)}</div>
              </div>
              <div className="bg-blue-50 rounded-lg p-4">
                <div className="text-sm text-blue-600">Staking</div>
                <div className="text-xl font-bold text-blue-900">{formatCad(data.income?.staking?.totalCad)}</div>
                <div className="text-xs text-blue-500">{formatAmount(data.income?.staking?.totalNear || 0)} NEAR</div>
              </div>
              <div className="bg-purple-50 rounded-lg p-4">
                <div className="text-sm text-purple-600">DeFi</div>
                <div className="text-xl font-bold text-purple-900">{formatCad(data.income?.defi?.totalCad)}</div>
              </div>
              <div className="bg-red-50 rounded-lg p-4">
                <div className="text-sm text-red-600">Expenses (Gas)</div>
                <div className="text-xl font-bold text-red-900">{formatCad(data.expenses?.total?.cad)}</div>
              </div>
            </div>
            <div className="bg-emerald-50 rounded-lg p-6">
              <div className="text-sm text-emerald-600">Net Income for {data.year}</div>
              <div className="text-3xl font-bold text-emerald-900">{formatCad(data.netIncome?.cad)}</div>
            </div>
            {data.income?.staking?.byValidator && data.income.staking.byValidator.length > 0 && (
              <div>
                <h3 className="font-semibold mb-2 dark:text-white">Staking by Validator</h3>
                <div className="bg-white border rounded-lg overflow-auto dark:bg-slate-800 dark:border-slate-600">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-50 dark:bg-slate-700">
                      <tr>
                        <th className="text-left px-4 py-2">Validator</th>
                        <th className="text-right px-4 py-2">Rewards (NEAR)</th>
                        <th className="text-right px-4 py-2">Value (CAD)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.income.staking.byValidator.map((v: any, i: number) => (
                        <tr key={i} className="border-t dark:border-slate-600">
                          <td className="px-4 py-2 font-mono text-xs">{v.validator}</td>
                          <td className="text-right px-4 py-2">{formatAmount(v.total_rewards)}</td>
                          <td className="text-right px-4 py-2">{formatCad(v.total_cad)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
            {data.notes && (
              <div className="text-sm text-slate-500 dark:text-slate-400 space-y-1">
                {data.notes.map((note: string, i: number) => (<div key={i}>• {note}</div>))}
              </div>
            )}
          </div>
        );

      default:
        return <div className="text-center py-8 text-slate-500">Select a report type</div>;
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold">Tax Reports</h1>
          <p className="text-slate-500">Complete tax reporting suite • Koinly-compatible</p>
        </div>
        <div className="flex items-center gap-4">
          <select
            value={year}
            onChange={(e) => setYear(e.target.value)}
            className="border rounded-lg px-4 py-2 bg-white"
          >
            <option value="2026">2026</option>
            <option value="2025">2025</option>
            <option value="2024">2024</option>
            <option value="2023">2023</option>
            <option value="2022">2022</option>
            <option value="2021">2021</option>
            <option value="2020">2020</option>
            <option value="2019">2019</option>
          </select>
          <button
            onClick={downloadCsv}
            className="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
          >
            <Download className="w-4 h-4" />
            Download CSV
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="mb-6 overflow-x-auto">
        <div className="flex gap-1 bg-slate-100 p-1 rounded-lg min-w-max">
          {tabs.map(tab => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm whitespace-nowrap transition-colors ${
                  activeTab === tab.id
                    ? 'bg-white text-blue-600 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-white/50'
                }`}
                title={tab.description}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Content */}
      <div className="bg-white rounded-lg shadow-sm border p-6">
        {renderContent()}
      </div>
    </div>
  );
}

'use client';

import { useState, useEffect } from 'react';
import { 
  FileText, 
  Download, 
  CheckCircle, 
  AlertCircle,
  Clock,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  DollarSign
} from 'lucide-react';

interface VerificationStatus {
  overall: 'pass' | 'warning' | 'error' | 'pending';
  wallets: Array<{
    address: string;
    chain: string;
    calculated: number;
    onChain: number;
    difference: number;
    status: 'pass' | 'warning' | 'error';
  }>;
  issues: Array<{
    type: string;
    severity: 'warning' | 'error';
    message: string;
    action: string;
  }>;
}

export default function ReportsPage() {
  const [selectedYear, setSelectedYear] = useState(2025);
  const [generating, setGenerating] = useState(false);
  const [reports, setReports] = useState<string[]>([]);
  const [verification, setVerification] = useState<VerificationStatus | null>(null);
  const [verifying, setVerifying] = useState(false);

  const reportTypes = [
    { id: 'capital_gains', name: 'Capital Gains Summary', description: 'All disposals with gain/loss calculations' },
    { id: 'income', name: 'Income Summary', description: 'Staking rewards, airdrops by month' },
    { id: 'ledger', name: 'Transaction Ledger', description: 'Complete transaction history' },
    { id: 't1135', name: 'T1135 Check', description: 'Foreign property threshold analysis' },
  ];

  const [selectedReports, setSelectedReports] = useState<string[]>(['capital_gains', 'income', 'ledger']);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      // Simulate report generation
      await new Promise(resolve => setTimeout(resolve, 2000));
      setReports(selectedReports);
    } catch (error) {
      console.error('Report generation failed:', error);
    } finally {
      setGenerating(false);
    }
  };

  const handleVerify = async () => {
    setVerifying(true);
    try {
      // Simulate verification
      await new Promise(resolve => setTimeout(resolve, 1500));
      setVerification({
        overall: 'warning',
        wallets: [
          { address: 'vitalpointai.near', chain: 'NEAR', calculated: 19763.45, onChain: 19763.93, difference: -0.48, status: 'pass' },
          { address: '0x1234...5678', chain: 'ETH', calculated: 2.5, onChain: 2.5, difference: 0, status: 'pass' },
        ],
        issues: [
          { type: 'duplicate', severity: 'warning', message: '2 potential duplicate transactions detected', action: 'Review transactions from Jan 15, 2025' },
        ],
      });
    } catch (error) {
      console.error('Verification failed:', error);
    } finally {
      setVerifying(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pass':
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case 'warning':
        return <AlertCircle className="w-5 h-5 text-yellow-500" />;
      case 'error':
        return <AlertCircle className="w-5 h-5 text-red-500" />;
      default:
        return <Clock className="w-5 h-5 text-slate-400" />;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Tax Reports</h1>
        <p className="text-slate-500">Generate and verify your tax reports</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Report Generator */}
        <div className="bg-white rounded-lg shadow-sm border p-6">
          <h2 className="text-lg font-semibold text-slate-700 mb-4">Generate Reports</h2>
          
          {/* Year selector */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-slate-600 mb-2">Tax Year</label>
            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(parseInt(e.target.value))}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value={2025}>2025</option>
              <option value={2024}>2024</option>
              <option value={2023}>2023</option>
            </select>
          </div>

          {/* Report type selection */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-slate-600 mb-2">Report Types</label>
            <div className="space-y-2">
              {reportTypes.map(report => (
                <label key={report.id} className="flex items-start gap-3 p-3 border rounded-lg cursor-pointer hover:bg-slate-50">
                  <input
                    type="checkbox"
                    checked={selectedReports.includes(report.id)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedReports([...selectedReports, report.id]);
                      } else {
                        setSelectedReports(selectedReports.filter(r => r !== report.id));
                      }
                    }}
                    className="mt-1"
                  />
                  <div>
                    <p className="font-medium text-slate-700">{report.name}</p>
                    <p className="text-sm text-slate-500">{report.description}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Generate button */}
          <button
            onClick={handleGenerate}
            disabled={generating || selectedReports.length === 0}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition disabled:opacity-50"
          >
            {generating ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <FileText className="w-4 h-4" />
                Generate Reports
              </>
            )}
          </button>

          {/* Download links */}
          {reports.length > 0 && (
            <div className="mt-6 pt-6 border-t">
              <h3 className="text-sm font-medium text-slate-600 mb-3">Ready for Download</h3>
              <div className="space-y-2">
                {reports.map(reportId => {
                  const report = reportTypes.find(r => r.id === reportId);
                  return (
                    <a
                      key={reportId}
                      href={`/api/reports/download?type=${reportId}&year=${selectedYear}`}
                      className="flex items-center justify-between p-3 border rounded-lg hover:bg-slate-50"
                    >
                      <span className="text-sm font-medium text-slate-700">{report?.name}</span>
                      <Download className="w-4 h-4 text-blue-500" />
                    </a>
                  );
                })}
                
                {/* Koinly format option */}
                <a
                  href={`/api/reports/download?format=koinly&year=${selectedYear}`}
                  className="flex items-center justify-between p-3 border rounded-lg hover:bg-slate-50 bg-blue-50"
                >
                  <span className="text-sm font-medium text-blue-700">📊 Koinly-Compatible CSV</span>
                  <Download className="w-4 h-4 text-blue-500" />
                </a>
              </div>
            </div>
          )}
        </div>

        {/* Verification Dashboard */}
        <div className="bg-white rounded-lg shadow-sm border p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-slate-700">Data Verification</h2>
            <button
              onClick={handleVerify}
              disabled={verifying}
              className="flex items-center gap-2 px-3 py-1.5 text-sm border rounded-lg hover:bg-slate-50"
            >
              <RefreshCw className={`w-4 h-4 ${verifying ? 'animate-spin' : ''}`} />
              Run Check
            </button>
          </div>

          {!verification ? (
            <div className="text-center py-8 text-slate-500">
              <CheckCircle className="w-12 h-12 mx-auto mb-3 text-slate-300" />
              <p>Click "Run Check" to verify your data</p>
              <p className="text-sm">Compares calculated balances against on-chain state</p>
            </div>
          ) : (
            <>
              {/* Overall status */}
              <div className={`flex items-center gap-3 p-4 rounded-lg mb-6 ${
                verification.overall === 'pass' ? 'bg-green-50' :
                verification.overall === 'warning' ? 'bg-yellow-50' : 'bg-red-50'
              }`}>
                {getStatusIcon(verification.overall)}
                <div>
                  <p className="font-medium text-slate-800">
                    {verification.overall === 'pass' ? 'All Clear' :
                     verification.overall === 'warning' ? 'Issues Found' : 'Action Required'}
                  </p>
                  <p className="text-sm text-slate-600">
                    {verification.issues.length} issue(s) detected
                  </p>
                </div>
              </div>

              {/* Wallet reconciliation */}
              <div className="mb-6">
                <h3 className="text-sm font-medium text-slate-600 mb-3">Wallet Reconciliation</h3>
                <div className="space-y-2">
                  {verification.wallets.map((wallet, i) => (
                    <div key={i} className="flex items-center justify-between p-3 border rounded-lg">
                      <div>
                        <p className="text-sm font-medium text-slate-700">{wallet.address}</p>
                        <p className="text-xs text-slate-500">{wallet.chain}</p>
                      </div>
                      <div className="text-right">
                        <div className="flex items-center gap-2">
                          {getStatusIcon(wallet.status)}
                          <span className={`text-sm font-mono ${
                            Math.abs(wallet.difference) < 0.01 ? 'text-green-600' : 'text-yellow-600'
                          }`}>
                            {wallet.difference > 0 ? '+' : ''}{wallet.difference.toFixed(4)}
                          </span>
                        </div>
                        <p className="text-xs text-slate-400">
                          Calc: {wallet.calculated.toFixed(2)} | Chain: {wallet.onChain.toFixed(2)}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Issues */}
              {verification.issues.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-slate-600 mb-3">Issues to Review</h3>
                  <div className="space-y-2">
                    {verification.issues.map((issue, i) => (
                      <div key={i} className={`p-3 rounded-lg ${
                        issue.severity === 'error' ? 'bg-red-50 border border-red-200' : 'bg-yellow-50 border border-yellow-200'
                      }`}>
                        <div className="flex items-start gap-2">
                          <AlertCircle className={`w-4 h-4 mt-0.5 ${
                            issue.severity === 'error' ? 'text-red-500' : 'text-yellow-500'
                          }`} />
                          <div>
                            <p className="text-sm font-medium text-slate-700">{issue.message}</p>
                            <p className="text-xs text-slate-500 mt-1">
                              <strong>Action:</strong> {issue.action}
                            </p>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard
          icon={TrendingUp}
          label="Capital Gains"
          value="$0.00"
          color="green"
        />
        <StatCard
          icon={TrendingDown}
          label="Capital Losses"
          value="$0.00"
          color="red"
        />
        <StatCard
          icon={DollarSign}
          label="Taxable Income"
          value="$0.00"
          color="blue"
        />
        <StatCard
          icon={FileText}
          label="Transactions"
          value="0"
          color="purple"
        />
      </div>
    </div>
  );
}

function StatCard({ 
  icon: Icon, 
  label, 
  value, 
  color 
}: { 
  icon: React.ComponentType<{ className?: string }>;
  label: string; 
  value: string; 
  color: 'green' | 'red' | 'blue' | 'purple';
}) {
  const colors = {
    green: 'bg-green-50 text-green-600',
    red: 'bg-red-50 text-red-600',
    blue: 'bg-blue-50 text-blue-600',
    purple: 'bg-purple-50 text-purple-600',
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border p-4">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg ${colors[color]}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <p className="text-sm text-slate-500">{label}</p>
          <p className="text-xl font-bold text-slate-900">{value}</p>
        </div>
      </div>
    </div>
  );
}

'use client';

import { useAuth } from '@/components/auth-provider';
import { PortfolioSummary } from '@/components/portfolio-summary';
import { HoldingsChart } from '@/components/holdings-chart';
import { StakingPositions } from '@/components/staking-positions';
import { ArrowLeftRight, Plus } from 'lucide-react';
import Link from 'next/link';

export default function DashboardPage() {
  const { user } = useAuth();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
          <p className="text-slate-500">
            Welcome back, {user?.nearAccountId}
          </p>
        </div>
        <Link
          href="/dashboard/wallets"
          className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition"
        >
          <Plus className="w-4 h-4" />
          Add Wallet
        </Link>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Portfolio Summary - spans 2 columns on large screens */}
        <div className="lg:col-span-2">
          <PortfolioSummary />
        </div>

        {/* Quick Actions */}
        <div className="bg-white rounded-lg shadow-sm border p-6">
          <h2 className="text-lg font-semibold text-slate-700 mb-4">Quick Actions</h2>
          <div className="space-y-3">
            <Link
              href="/dashboard/wallets"
              className="flex items-center gap-3 p-3 border rounded-lg hover:bg-slate-50 transition"
            >
              <div className="p-2 bg-blue-50 rounded-lg">
                <Plus className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <p className="font-medium text-slate-800">Add Wallet</p>
                <p className="text-xs text-slate-500">Connect NEAR, ETH, or other chains</p>
              </div>
            </Link>
            <Link
              href="/dashboard/transactions"
              className="flex items-center gap-3 p-3 border rounded-lg hover:bg-slate-50 transition"
            >
              <div className="p-2 bg-green-50 rounded-lg">
                <ArrowLeftRight className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <p className="font-medium text-slate-800">View Transactions</p>
                <p className="text-xs text-slate-500">Browse and filter your history</p>
              </div>
            </Link>
            <Link
              href="/dashboard/reports"
              className="flex items-center gap-3 p-3 border rounded-lg hover:bg-slate-50 transition"
            >
              <div className="p-2 bg-purple-50 rounded-lg">
                <svg className="w-5 h-5 text-purple-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <div>
                <p className="font-medium text-slate-800">Generate Reports</p>
                <p className="text-xs text-slate-500">Tax reports for 2025</p>
              </div>
            </Link>
          </div>
        </div>
      </div>

      {/* Holdings and Staking */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <HoldingsChart />
        <StakingPositions />
      </div>

      {/* Recent Activity */}
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-slate-700">Recent Activity</h2>
          <Link href="/dashboard/transactions" className="text-sm text-blue-500 hover:underline">
            View all
          </Link>
        </div>
        <RecentTransactions />
      </div>
    </div>
  );
}

function RecentTransactions() {
  // This would fetch recent transactions
  return (
    <div className="text-center py-8 text-slate-500">
      <ArrowLeftRight className="w-12 h-12 mx-auto mb-3 text-slate-300" />
      <p>No recent transactions</p>
      <p className="text-sm">Sync a wallet to see activity</p>
    </div>
  );
}

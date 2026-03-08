'use client';

import { useAuth } from '@/components/auth-provider';
import { PortfolioSummary } from '@/components/portfolio-summary';
import { PortfolioChart } from '@/components/portfolio-chart';
import { HoldingsChart } from '@/components/holdings-chart';
import { StakingPositions } from '@/components/staking-positions';
import { WalletVerification } from '@/components/wallet-verification';
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

      {/* Row 1: Portfolio Summary + Chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <PortfolioSummary />
        </div>
        <div>
          <PortfolioChart />
        </div>
      </div>

      {/* Row 2: Wallet Verification - Full Width */}
      <WalletVerification />

      {/* Row 3: Holdings and Staking */}
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
  return (
    <div className="text-center py-8 text-slate-500">
      <ArrowLeftRight className="w-12 h-12 mx-auto mb-3 text-slate-300" />
      <p>No recent transactions</p>
      <p className="text-sm">Sync a wallet to see activity</p>
    </div>
  );
}

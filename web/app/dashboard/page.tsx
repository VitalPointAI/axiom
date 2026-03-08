'use client';

import { useAuth } from '@/components/auth-provider';
import { PortfolioSummary } from '@/components/portfolio-summary';
import { PortfolioChart } from '@/components/portfolio-chart';
import { WalletVerification } from '@/components/wallet-verification';
import { Plus } from 'lucide-react';
import Link from 'next/link';

export default function DashboardPage() {
  const { user } = useAuth();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Dashboard</h1>
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

      {/* Portfolio Summary */}
      <PortfolioSummary />

      {/* Portfolio History - Full Width */}
      <PortfolioChart />

      {/* Wallet Verification - Full Width */}
      <WalletVerification />
    </div>
  );
}

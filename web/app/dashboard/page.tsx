'use client';

import { useAuth } from '@/components/auth-provider';
import { 
  Wallet, 
  ArrowLeftRight, 
  TrendingUp,
  AlertCircle 
} from 'lucide-react';

export default function DashboardPage() {
  const { user } = useAuth();

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-slate-500">
          Welcome back, {user?.nearAccountId}
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Total Portfolio"
          value="$0.00"
          subtext="0 assets"
          icon={TrendingUp}
          color="blue"
        />
        <StatCard
          title="Wallets"
          value="0"
          subtext="Connected"
          icon={Wallet}
          color="green"
        />
        <StatCard
          title="Transactions"
          value="0"
          subtext="This year"
          icon={ArrowLeftRight}
          color="purple"
        />
        <StatCard
          title="Issues"
          value="0"
          subtext="Need attention"
          icon={AlertCircle}
          color="orange"
        />
      </div>

      {/* Quick Actions */}
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Get Started</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <QuickAction
            title="Add Wallet"
            description="Connect your NEAR, ETH, or other wallets"
            href="/dashboard/wallets"
          />
          <QuickAction
            title="Import Exchange Data"
            description="Upload CSV from Coinbase, Crypto.com, etc."
            href="/dashboard/wallets"
          />
          <QuickAction
            title="Generate Report"
            description="Create tax reports for 2025"
            href="/dashboard/reports"
          />
        </div>
      </div>

      {/* Recent Activity */}
      <div className="bg-white rounded-lg shadow-sm border p-6">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">Recent Activity</h2>
        <div className="text-center py-8 text-slate-500">
          <ArrowLeftRight className="w-12 h-12 mx-auto mb-3 text-slate-300" />
          <p>No transactions yet</p>
          <p className="text-sm">Add a wallet to start syncing your transaction history</p>
        </div>
      </div>
    </div>
  );
}

function StatCard({ 
  title, 
  value, 
  subtext, 
  icon: Icon,
  color 
}: { 
  title: string; 
  value: string; 
  subtext: string;
  icon: React.ComponentType<{ className?: string }>;
  color: 'blue' | 'green' | 'purple' | 'orange';
}) {
  const colors = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    purple: 'bg-purple-50 text-purple-600',
    orange: 'bg-orange-50 text-orange-600',
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border p-6">
      <div className="flex items-center gap-4">
        <div className={`p-3 rounded-lg ${colors[color]}`}>
          <Icon className="w-6 h-6" />
        </div>
        <div>
          <p className="text-sm text-slate-500">{title}</p>
          <p className="text-2xl font-bold text-slate-900">{value}</p>
          <p className="text-xs text-slate-400">{subtext}</p>
        </div>
      </div>
    </div>
  );
}

function QuickAction({ 
  title, 
  description, 
  href 
}: { 
  title: string; 
  description: string; 
  href: string;
}) {
  return (
    <a
      href={href}
      className="block p-4 border rounded-lg hover:border-slate-300 hover:bg-slate-50 transition"
    >
      <h3 className="font-medium text-slate-900">{title}</h3>
      <p className="text-sm text-slate-500 mt-1">{description}</p>
    </a>
  );
}

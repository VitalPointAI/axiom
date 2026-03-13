'use client';

import { useAuth } from '@/components/auth-provider';
import { PortfolioSummary } from '@/components/portfolio-summary';
import { Plus, AlertTriangle } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api';

interface NeedsReviewCount {
  total: number;
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [needsReview, setNeedsReview] = useState<number>(0);

  useEffect(() => {
    apiClient
      .get<NeedsReviewCount>('/api/verification/needs-review-count')
      .then((d) => setNeedsReview(d.total))
      .catch(() => {
        // Non-critical — ignore errors on the badge
      });
  }, []);

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
        <div className="flex items-center gap-3">
          {needsReview > 0 && (
            <Link
              href="/dashboard/transactions"
              className="flex items-center gap-2 px-3 py-2 bg-amber-50 border border-amber-200 text-amber-700 rounded-lg hover:bg-amber-100 transition text-sm"
            >
              <AlertTriangle className="w-4 h-4" />
              {needsReview} need{needsReview === 1 ? 's' : ''} review
            </Link>
          )}
          <Link
            href="/dashboard/wallets"
            className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition"
          >
            <Plus className="w-4 h-4" />
            Add Wallet
          </Link>
        </div>
      </div>

      {/* Portfolio Summary */}
      <PortfolioSummary />
    </div>
  );
}

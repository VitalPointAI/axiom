'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { CheckCircle, Loader2, ChevronRight, FileText, Search, BarChart3 } from 'lucide-react';
import { apiClient } from '@/lib/api';

interface ReviewStepProps {
  onNext: () => void;
  onSkip: () => void;
}

interface WalletsResponse {
  wallets: Array<{ id: number; account_id: string; chain: string }>;
}

interface TransactionsResponse {
  total: number;
}

export function ReviewStep({ onNext: _onNext, onSkip: _onSkip }: ReviewStepProps) {
  const router = useRouter();
  const [walletCount, setWalletCount] = useState<number | null>(null);
  const [txCount, setTxCount] = useState<number | null>(null);
  const [completing, setCompleting] = useState(false);

  useEffect(() => {
    const fetchSummary = async () => {
      try {
        const [walletsData, txData] = await Promise.all([
          apiClient.get<WalletsResponse>('/api/wallets'),
          apiClient.get<TransactionsResponse>('/api/transactions?limit=1').catch(() => ({ total: 0 })),
        ]);
        setWalletCount((walletsData.wallets || []).length);
        setTxCount(txData.total ?? 0);
      } catch (err) {
        console.error('Failed to fetch review summary:', err);
        setWalletCount(0);
        setTxCount(0);
      }
    };

    fetchSummary();
  }, []);

  const handleGoToDashboard = async () => {
    if (completing) return;
    setCompleting(true);
    try {
      await apiClient.post('/api/preferences/complete-onboarding');
    } catch (err) {
      console.error('Failed to complete onboarding:', err);
    }
    router.replace('/dashboard');
  };

  const ORIENTATION_LINKS = [
    {
      href: '/dashboard/reports',
      icon: <FileText className="w-5 h-5 text-blue-400" />,
      title: 'Reports',
      description: 'View your tax reports, capital gains, and income summaries',
    },
    {
      href: '/dashboard/transactions',
      icon: <Search className="w-5 h-5 text-purple-400" />,
      title: 'Transactions',
      description: 'Review and edit individual transaction classifications',
    },
    {
      href: '/dashboard/wallets',
      icon: <BarChart3 className="w-5 h-5 text-green-400" />,
      title: 'Verification',
      description: 'Check wallet sync status and balance reconciliation',
    },
  ];

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 space-y-6">
      {/* Header */}
      <div className="text-center space-y-2">
        <div className="w-14 h-14 bg-green-600 rounded-full flex items-center justify-center mx-auto">
          <CheckCircle className="w-8 h-8 text-white" />
        </div>
        <h2 className="text-2xl font-bold text-white">You&apos;re all set!</h2>
        <p className="text-gray-400 text-sm">Here&apos;s a summary of what was imported.</p>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-gray-900 rounded-lg p-4 text-center">
          {walletCount === null ? (
            <Loader2 className="w-5 h-5 animate-spin text-gray-500 mx-auto" />
          ) : (
            <p className="text-3xl font-bold text-white">{walletCount}</p>
          )}
          <p className="text-xs text-gray-400 mt-1">Wallets added</p>
        </div>
        <div className="bg-gray-900 rounded-lg p-4 text-center">
          {txCount === null ? (
            <Loader2 className="w-5 h-5 animate-spin text-gray-500 mx-auto" />
          ) : (
            <p className="text-3xl font-bold text-white">
              {txCount > 0 ? txCount.toLocaleString() : '—'}
            </p>
          )}
          <p className="text-xs text-gray-400 mt-1">Transactions found</p>
        </div>
      </div>

      {/* Expectations note */}
      <div className="bg-amber-900/20 border border-amber-700/50 rounded-lg p-4">
        <p className="text-amber-300 text-sm">
          <strong>Note:</strong> Some items may be flagged for review. This is normal — Axiom flags
          anything it&apos;s not 100% sure about so you can confirm before generating tax reports.
        </p>
      </div>

      {/* Orientation links */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-300 uppercase tracking-wide">
          Where to go from here
        </h3>
        <div className="space-y-2">
          {ORIENTATION_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="flex items-center gap-4 bg-gray-900 border border-gray-700 hover:border-gray-500 rounded-lg px-4 py-3 transition-colors group"
            >
              <div className="flex-shrink-0">{link.icon}</div>
              <div className="flex-1">
                <p className="text-white font-medium text-sm group-hover:text-blue-300 transition-colors">
                  {link.title}
                </p>
                <p className="text-gray-500 text-xs">{link.description}</p>
              </div>
              <ChevronRight className="w-4 h-4 text-gray-600 group-hover:text-gray-400 transition-colors" />
            </a>
          ))}
        </div>
      </div>

      {/* Go to Dashboard */}
      <button
        onClick={handleGoToDashboard}
        disabled={completing}
        className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white font-semibold rounded-lg transition-colors"
      >
        {completing ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Redirecting...
          </>
        ) : (
          <>
            Go to Dashboard
            <ChevronRight className="w-4 h-4" />
          </>
        )}
      </button>
    </div>
  );
}

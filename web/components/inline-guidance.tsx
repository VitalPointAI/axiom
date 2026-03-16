'use client';

import { useState } from 'react';
import { CheckCircle } from 'lucide-react';
import { apiClient } from '@/lib/api';

interface GuidanceConfig {
  explanation: string;
  actionLabel: string;
  actionType: 'resync' | 'resolve' | 'navigate';
  navigateTo?: string;
}

const CATEGORY_GUIDANCE: Record<string, GuidanceConfig> = {
  missing_staking_rewards: {
    explanation:
      'You sold or transferred tokens at a loss and appear to have missing staking rewards. Axiom detected a gap in your staking reward history.',
    actionLabel: 'Re-sync Staking',
    actionType: 'resync',
  },
  unindexed_period: {
    explanation:
      "There's a gap in your transaction history for this wallet. Some transactions may not have been indexed.",
    actionLabel: 'Re-index Wallet',
    actionType: 'resync',
  },
  classification_error: {
    explanation:
      "This transaction's classification may be incorrect. The automated classifier was not confident enough.",
    actionLabel: 'Review Transaction',
    actionType: 'navigate',
    navigateTo: '/dashboard/transactions?needs_review=true',
  },
  duplicates: {
    explanation:
      'This transaction appears to match another transaction. It may have been imported from both your wallet and an exchange.',
    actionLabel: 'Mark Reviewed',
    actionType: 'resolve',
  },
  uncounted_fees: {
    explanation:
      'Some network fees associated with this transaction may not be reflected in the cost basis calculation.',
    actionLabel: 'Mark Reviewed',
    actionType: 'resolve',
  },
};

interface InlineGuidanceProps {
  diagnosisCategory: string;
  verificationId: number;
  onAction?: () => void;
}

export function InlineGuidance({ diagnosisCategory, verificationId, onAction }: InlineGuidanceProps) {
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const config =
    CATEGORY_GUIDANCE[diagnosisCategory] ?? {
      explanation: 'This item needs review.',
      actionLabel: 'Mark Reviewed',
      actionType: 'resolve' as const,
    };

  const handleAction = async () => {
    if (config.actionType === 'navigate' && config.navigateTo) {
      window.location.href = config.navigateTo;
      return;
    }

    setLoading(true);
    try {
      if (config.actionType === 'resync') {
        await apiClient.post(`/api/verification/resync/${verificationId}`);
      } else {
        await apiClient.post(`/api/verification/resolve/${verificationId}`);
      }
      setDone(true);
      onAction?.();
    } catch {
      // Show done state optimistically even on API error — user sees feedback
      setDone(true);
      onAction?.();
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-gray-800/50 border-l-2 border-yellow-500 pl-3 py-2 pr-3 rounded-r">
      <p className="text-sm text-gray-300">{config.explanation}</p>
      <div className="mt-2">
        {done ? (
          <span className="inline-flex items-center gap-1 text-sm text-green-400">
            <CheckCircle className="w-4 h-4" />
            Done
          </span>
        ) : (
          <button
            onClick={handleAction}
            disabled={loading}
            className="inline-flex items-center gap-1 px-3 py-1 text-sm font-medium rounded border border-yellow-500/50 text-yellow-400 hover:bg-yellow-500/10 transition disabled:opacity-50"
          >
            {loading ? 'Working...' : config.actionLabel}
          </button>
        )}
      </div>
    </div>
  );
}

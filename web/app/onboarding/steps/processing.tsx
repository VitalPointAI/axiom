'use client';

import { useState, useEffect, useRef } from 'react';
import { Loader2, ChevronRight, Plus, X, Bell, Check } from 'lucide-react';
import { apiClient, ApiError } from '@/lib/api';
import { SyncStatus } from '@/components/sync-status';

interface ProcessingStepProps {
  onNext: () => void;
  onSkip: () => void;
}

interface ActiveJobsResponse {
  jobs: Array<{ status: string; pipeline_stage: string; pipeline_pct: number }>;
  pipeline_stage: string;
  pipeline_pct: number;
  estimated_minutes: number | null;
}

interface WalletSuggestion {
  address: string;
  chain: string;
  transfer_count: number;
  related_to: string;
}

interface SuggestionsResponse {
  suggestions: WalletSuggestion[];
}

export function ProcessingStep({ onNext, onSkip }: ProcessingStepProps) {
  const [suggestions, setSuggestions] = useState<WalletSuggestion[]>([]);
  const [dismissedSuggestions, setDismissedSuggestions] = useState<Set<string>>(new Set());
  const [addingWallet, setAddingWallet] = useState<string | null>(null);
  const [hasHadJobs, setHasHadJobs] = useState(false);
  const [isDone, setIsDone] = useState(false);
  const [estimatedMinutes, setEstimatedMinutes] = useState<number | null>(null);
  const [notifyRequested, setNotifyRequested] = useState(false);
  const [notifyLoading, setNotifyLoading] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const autoAdvancedRef = useRef(false);

  useEffect(() => {
    // Poll /api/jobs/active every 3 seconds
    const poll = async () => {
      try {
        const data = await apiClient.get<ActiveJobsResponse>('/api/jobs/active');
        const jobs = data.jobs || [];

        if (jobs.length > 0) {
          setHasHadJobs(true);
          setEstimatedMinutes(data.estimated_minutes);

          // Check if any jobs are at classifying stage or beyond — fetch suggestions
          const stage = (data.pipeline_stage || '').toLowerCase();
          if (
            stage.includes('classif') ||
            stage.includes('cost') ||
            stage.includes('acb') ||
            stage.includes('verif') ||
            stage.includes('done')
          ) {
            fetchSuggestions();
          }
        } else if (hasHadJobs && jobs.length === 0) {
          // Pipeline finished
          setIsDone(true);
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          // Auto-advance to review step after brief delay
          if (!autoAdvancedRef.current) {
            autoAdvancedRef.current = true;
            setTimeout(() => {
              onNext();
            }, 1500);
          }
        }
      } catch (err) {
        if (!(err instanceof ApiError)) {
          console.error('Failed to poll jobs:', err);
        }
      }
    };

    // Fetch suggestions after classifying stage
    const fetchSuggestions = async () => {
      try {
        const data = await apiClient.get<SuggestionsResponse>('/api/wallets/suggestions');
        setSuggestions(data.suggestions || []);
      } catch {
        // Suggestions are optional — ignore errors
      }
    };

    poll(); // Initial poll
    pollRef.current = setInterval(poll, 3000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Separate effect for hasHadJobs changes (can't include in deps above due to stale closure)
  useEffect(() => {
    if (!isDone) return;
    if (!autoAdvancedRef.current) {
      autoAdvancedRef.current = true;
      setTimeout(() => {
        onNext();
      }, 1500);
    }
  }, [isDone, onNext]);

  const handleAddSuggested = async (suggestion: WalletSuggestion) => {
    setAddingWallet(suggestion.address);
    try {
      await apiClient.post('/api/wallets', {
        account_id: suggestion.address,
        chain: suggestion.chain,
      });
      setDismissedSuggestions((prev) => new Set([...prev, suggestion.address]));
    } catch (err) {
      console.error('Failed to add suggested wallet:', err);
    }
    setAddingWallet(null);
  };

  const handleDismissSuggestion = (address: string) => {
    setDismissedSuggestions((prev) => new Set([...prev, address]));
  };

  const handleNotifyMe = async () => {
    setNotifyLoading(true);
    try {
      await apiClient.post('/api/jobs/notify-when-done', {});
      setNotifyRequested(true);
    } catch {
      // Silently fail — button stays available to retry
    }
    setNotifyLoading(false);
  };

  const visibleSuggestions = suggestions.filter(
    (s) => !dismissedSuggestions.has(s.address)
  );

  const truncateAddress = (addr: string) => {
    if (addr.length <= 16) return addr;
    return `${addr.slice(0, 8)}...${addr.slice(-6)}`;
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 space-y-6">
      {/* Header */}
      <div className="text-center space-y-2">
        {isDone ? (
          <>
            <div className="w-12 h-12 bg-green-600 rounded-full flex items-center justify-center mx-auto">
              <span className="text-white text-2xl">✓</span>
            </div>
            <h2 className="text-xl font-bold text-white">Processing Complete!</h2>
            <p className="text-gray-400 text-sm">Redirecting to review...</p>
          </>
        ) : (
          <>
            <Loader2 className="w-10 h-10 text-blue-400 animate-spin mx-auto" />
            <h2 className="text-xl font-bold text-white">We&apos;re crunching your data...</h2>
            <p className="text-gray-400 text-sm">
              Axiom is indexing your transactions, classifying them, calculating cost basis, and
              verifying balances.
              {estimatedMinutes !== null && estimatedMinutes <= 5
                ? ' This should take about ' + estimatedMinutes + (estimatedMinutes === 1 ? ' minute.' : ' minutes.')
                : estimatedMinutes !== null && estimatedMinutes <= 30
                  ? ' Estimated time: about ' + estimatedMinutes + ' minutes.'
                  : estimatedMinutes !== null
                    ? ' Estimated time: about ' + Math.round(estimatedMinutes / 60) + (Math.round(estimatedMinutes / 60) === 1 ? ' hour.' : ' hours.')
                    : ' This may take a few minutes.'}
            </p>
            <p className="text-gray-500 text-xs mt-1">
              Indexing continues in the background — you can close this page and come back later.
            </p>
          </>
        )}
      </div>

      {/* SyncStatus pipeline progress */}
      {!isDone && (
        <div className="bg-gray-900 rounded-lg p-4">
          <SyncStatus />
        </div>
      )}

      {/* Notify me button — show when estimate is > 5 min */}
      {!isDone && estimatedMinutes !== null && estimatedMinutes > 5 && (
        <div className="flex justify-center">
          {notifyRequested ? (
            <div className="flex items-center gap-2 text-green-400 text-sm py-2">
              <Check className="w-4 h-4" />
              <span>We&apos;ll email you when it&apos;s done</span>
            </div>
          ) : (
            <button
              onClick={handleNotifyMe}
              disabled={notifyLoading}
              className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-gray-200 text-sm rounded-lg transition-colors"
            >
              {notifyLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Bell className="w-4 h-4" />
              )}
              Notify me when done
            </button>
          )}
        </div>
      )}

      {/* Wallet discovery section */}
      {visibleSuggestions.length > 0 && (
        <div className="space-y-3">
          <div className="border-t border-gray-700 pt-4">
            <h3 className="text-sm font-semibold text-white mb-1">
              We found wallets that might be yours
            </h3>
            <p className="text-xs text-gray-400 mb-3">
              These addresses were found connected to your wallets. Add them to track all your
              activity.
            </p>
            <div className="space-y-2">
              {visibleSuggestions.map((suggestion) => (
                <div
                  key={suggestion.address}
                  className="flex items-center justify-between bg-gray-900 border border-gray-700 rounded-lg px-3 py-2"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-400 font-medium">{suggestion.chain}</span>
                      <code className="text-xs text-white font-mono">
                        {truncateAddress(suggestion.address)}
                      </code>
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {suggestion.transfer_count} transfers from {suggestion.related_to}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 ml-3">
                    <button
                      onClick={() => handleAddSuggested(suggestion)}
                      disabled={addingWallet === suggestion.address}
                      className="flex items-center gap-1 px-2 py-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs rounded transition-colors"
                    >
                      {addingWallet === suggestion.address ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <Plus className="w-3 h-3" />
                      )}
                      Add
                    </button>
                    <button
                      onClick={() => handleDismissSuggestion(suggestion.address)}
                      className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                      title="Not my wallet"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Skip action */}
      <div className="pt-2">
        <button
          onClick={onSkip}
          className="w-full text-sm text-gray-400 hover:text-gray-300 transition-colors py-2 flex items-center justify-center gap-1"
        >
          Go to dashboard — indexing will continue in the background
          <ChevronRight className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}

'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { WelcomeStep } from './steps/welcome';
import { WalletsStep } from './steps/wallets';
import { ImportStep } from './steps/import';
import { ProcessingStep } from './steps/processing';
import { ReviewStep } from './steps/review';

interface WalletsResponse {
  wallets: Array<{ id: number; account_id: string; chain: string }>;
}

interface ActiveJobsResponse {
  jobs: Array<{ status: string; pipeline_stage: string }>;
}

interface PreferencesResponse {
  onboarding_completed_at: string | null;
  dismissed_banners: Record<string, boolean>;
}

const STEP_NAMES = [
  'Welcome',
  'Add Wallets',
  'Import Exchanges',
  'Processing',
  'Review',
];

export default function OnboardingPage() {
  const router = useRouter();
  const [step, setStep] = useState<number | null>(null); // null = loading
  const [isSkipping, setIsSkipping] = useState(false);
  const [hasWallets, setHasWallets] = useState(false);

  useEffect(() => {
    const determineStep = async () => {
      try {
        const [walletsData, jobsData, prefsData] = await Promise.all([
          apiClient.get<WalletsResponse>('/api/wallets'),
          apiClient.get<ActiveJobsResponse>('/api/jobs/active'),
          apiClient.get<PreferencesResponse>('/api/preferences'),
        ]);

        const prefs = prefsData;
        const wallets = walletsData.wallets || [];
        const activeJobs = jobsData.jobs || [];

        if (wallets.length > 0) setHasWallets(true);

        // Already completed onboarding — redirect to dashboard
        if (prefs.onboarding_completed_at) {
          router.replace('/dashboard');
          return;
        }

        // No wallets — start at Step 1 (Welcome)
        if (wallets.length === 0) {
          setStep(1);
          return;
        }

        // Has wallets + active jobs — Step 4 (Processing)
        if (activeJobs.length > 0) {
          setStep(4);
          return;
        }

        // Has wallets + no active jobs — check if pipeline ran
        // Try to determine if processing completed by checking for transactions
        try {
          const txData = await apiClient.get<{ total: number }>('/api/transactions?limit=1');
          if (txData.total > 0) {
            // Pipeline ran and produced transactions — Step 5 (Review)
            setStep(5);
          } else {
            // Has wallets but no transactions yet — Step 3 (Import)
            setStep(3);
          }
        } catch {
          // Fallback to Step 3 if transactions check fails
          setStep(3);
        }
      } catch (err) {
        console.error('Failed to determine onboarding step:', err);
        // Default to Step 1 on error
        setStep(1);
      }
    };

    determineStep();
  }, [router]);

  const handleNext = () => {
    setStep((s) => {
      if (s === null) return 1;
      // Skip "Add Wallets" step if user already has wallets
      if (s === 1 && hasWallets) return 3;
      return Math.min(s + 1, 5);
    });
  };

  const handleSkipToDashboard = async () => {
    if (isSkipping) return;
    setIsSkipping(true);
    try {
      await apiClient.post('/api/preferences/complete-onboarding');
    } catch (err) {
      console.error('Failed to mark onboarding complete:', err);
    }
    router.replace('/dashboard');
  };

  if (step === null) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Step indicator */}
      <div className="flex items-center justify-between px-1">
        {STEP_NAMES.map((name, idx) => {
          const stepNum = idx + 1;
          const isActive = stepNum === step;
          const isComplete = stepNum < step;
          return (
            <div key={name} className="flex items-center">
              <div className="flex flex-col items-center gap-1">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all ${
                    isComplete
                      ? 'bg-green-500 border-green-500 text-white'
                      : isActive
                      ? 'bg-blue-500 border-blue-400 text-white'
                      : 'bg-gray-800 border-gray-600 text-gray-500'
                  }`}
                >
                  {isComplete ? '✓' : stepNum}
                </div>
                <span
                  className={`text-xs hidden sm:block ${
                    isActive ? 'text-white font-medium' : isComplete ? 'text-green-400' : 'text-gray-500'
                  }`}
                >
                  {name}
                </span>
              </div>
              {idx < STEP_NAMES.length - 1 && (
                <div
                  className={`flex-1 h-0.5 mx-2 mb-5 transition-all ${
                    isComplete ? 'bg-green-500' : 'bg-gray-700'
                  }`}
                  style={{ minWidth: '20px' }}
                />
              )}
            </div>
          );
        })}
      </div>

      {/* Step content */}
      <div>
        {step === 1 && (
          <WelcomeStep onNext={handleNext} onSkip={handleSkipToDashboard} />
        )}
        {step === 2 && (
          <WalletsStep onNext={handleNext} onSkip={handleSkipToDashboard} />
        )}
        {step === 3 && (
          <ImportStep onNext={handleNext} onSkip={handleSkipToDashboard} />
        )}
        {step === 4 && (
          <ProcessingStep onNext={handleNext} onSkip={handleSkipToDashboard} />
        )}
        {step === 5 && (
          <ReviewStep onNext={handleNext} onSkip={handleSkipToDashboard} />
        )}
      </div>

      {/* Step counter */}
      <div className="text-center text-xs text-gray-500">
        Step {step} of 5
      </div>
    </div>
  );
}

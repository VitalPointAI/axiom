'use client';

import { useAuth } from '@/components/auth-provider';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { apiClient } from '@/lib/api';

interface PreferencesResponse {
  onboarding_completed_at: string | null;
  dismissed_banners: Record<string, boolean>;
}

export default function OnboardingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace('/auth');
      return;
    }

    if (!isLoading && user) {
      // Check if onboarding already completed — redirect to dashboard
      const checkOnboarding = async () => {
        try {
          const prefs = await apiClient.get<PreferencesResponse>('/api/preferences');
          if (prefs.onboarding_completed_at) {
            router.replace('/dashboard');
            return;
          }
        } catch (err) {
          // If preferences check fails, allow user into onboarding
          console.error('Failed to check onboarding status:', err);
        }
        setChecking(false);
      };
      checkOnboarding();
    }
  }, [user, isLoading, router]);

  if (isLoading || checking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        {children}
      </div>
    </div>
  );
}

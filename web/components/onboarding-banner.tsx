'use client';

import { useState, useEffect } from 'react';
import { Info, X } from 'lucide-react';
import { apiClient } from '@/lib/api';

interface PreferencesResponse {
  onboarding_completed_at: string | null;
  dismissed_banners: Record<string, boolean>;
}

interface OnboardingBannerProps {
  bannerKey: string;
  title: string;
  description: string;
  icon?: React.ReactNode;
}

export function OnboardingBanner({ bannerKey, title, description, icon }: OnboardingBannerProps) {
  const [visible, setVisible] = useState(false);
  const [dismissing, setDismissing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .get<PreferencesResponse>('/api/preferences')
      .then((prefs) => {
        if (!cancelled) {
          const isDismissed = prefs?.dismissed_banners?.[bannerKey] === true;
          setVisible(!isDismissed);
        }
      })
      .catch(() => {
        // If preferences fetch fails, show the banner — better to show than silently hide
        if (!cancelled) {
          setVisible(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [bannerKey]);

  const handleDismiss = async () => {
    setDismissing(true);
    setVisible(false);
    try {
      await apiClient.patch('/api/preferences/dismiss-banner', { banner_key: bannerKey });
    } catch {
      // Dismissal failure is non-critical; banner is already hidden via local state
    } finally {
      setDismissing(false);
    }
  };

  if (!visible) return null;

  return (
    <div className="mb-6 flex items-start gap-3 bg-blue-900/30 border border-blue-800 rounded-lg p-4">
      <div className="flex-shrink-0 mt-0.5 text-blue-400">
        {icon ?? <Info className="w-5 h-5" />}
      </div>
      <div className="flex-1 min-w-0">
        <p className="font-medium text-blue-300">{title}</p>
        <p className="mt-1 text-sm text-blue-200/70">{description}</p>
      </div>
      <button
        onClick={handleDismiss}
        disabled={dismissing}
        aria-label="Dismiss banner"
        className="flex-shrink-0 p-1 rounded hover:bg-blue-800/50 transition text-blue-400 hover:text-blue-200 disabled:opacity-50"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

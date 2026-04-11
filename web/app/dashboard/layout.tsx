'use client';

import { AuthProvider, useAuth } from '@/components/auth-provider';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Sidebar } from '@/components/sidebar';
import { SyncStatus } from '@/components/sync-status';
import { Tally } from '@/components/tally';
import { ClientSwitcher } from '@/components/client-switcher';
import { Loader2 } from 'lucide-react';
import { apiClient } from '@/lib/api';

interface PreferencesResponse {
  onboarding_completed_at: string | null;
  dismissed_banners: Record<string, boolean>;
}

interface WalletsResponse {
  wallets: Array<{ id: number; account_id: string; chain: string }>;
}

function DashboardLayoutInner({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const [isViewingClient, setIsViewingClient] = useState(false);
  const [onboardingChecked, setOnboardingChecked] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace('/auth');
    }
  }, [user, isLoading, router]);

  // Onboarding check: redirect new users (no wallets + NULL onboarding_completed_at) to /onboarding
  // IMPORTANT: Existing users with wallets but NULL timestamp must NOT be redirected (pitfall #2)
  useEffect(() => {
    if (isLoading || !user) return;

    const checkOnboarding = async () => {
      try {
        const prefs = await apiClient.get<PreferencesResponse>('/api/preferences');

        // If onboarding already completed, no redirect needed
        if (prefs.onboarding_completed_at) {
          setOnboardingChecked(true);
          return;
        }

        // Only redirect if BOTH conditions are true: NULL timestamp AND zero wallets
        const walletsData = await apiClient.get<WalletsResponse>('/api/wallets');
        const wallets = walletsData.wallets || [];

        if (wallets.length === 0) {
          // New user with no wallets — send to onboarding
          router.replace('/onboarding');
          return;
        }

        // Existing user with wallets but NULL onboarding_completed_at — allow dashboard access
        setOnboardingChecked(true);
      } catch (err) {
        // If check fails, do NOT redirect — non-blocking
        console.error('Onboarding check failed (non-blocking):', err);
        setOnboardingChecked(true);
      }
    };

    checkOnboarding();
  }, [user, isLoading, router]);

  // Check if viewing as client (for top padding)
  useEffect(() => {
    const checkViewingStatus = async () => {
      try {
        const res = await fetch('/api/accountant/switch');
        if (res.ok) {
          const data = await res.json();
          setIsViewingClient(!!data.currentlyViewing);
        }
      } catch (e) {
        // Ignore
      }
    };
    if (user) {
      checkViewingStatus();
    }
  }, [user]);

  if (isLoading || !onboardingChecked) {
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
    <div className={`min-h-screen flex bg-gray-900 ${isViewingClient ? 'pt-8' : ''}`}>
      <Sidebar user={user} />
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header with padding for mobile menu button */}
        <header className="h-14 border-b border-gray-800 bg-gray-900/50 backdrop-blur px-4 lg:px-6 flex items-center justify-between">
          {/* Spacer for mobile menu button */}
          <div className="lg:hidden w-10" />
          <div className="text-sm text-gray-400 truncate">
            Welcome, <span className="text-white font-medium">{user.display_name}</span>
          </div>
          <div className="flex items-center gap-3">
            <ClientSwitcher />
            <SyncStatus />
          </div>
        </header>
        <main className="flex-1 p-4 lg:p-6 overflow-auto">
          {children}
        </main>
      </div>

      {/* Tally AI Assistant */}
      <Tally />
    </div>
  );
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthProvider>
      <DashboardLayoutInner>{children}</DashboardLayoutInner>
    </AuthProvider>
  );
}

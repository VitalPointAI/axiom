'use client';

import { useAuth } from '@/components/auth-provider';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Sidebar } from '@/components/sidebar';
import { SyncStatus } from '@/components/sync-status';
import { Tally } from '@/components/tally';
import { ClientSwitcher } from '@/components/client-switcher';
import { Loader2 } from 'lucide-react';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const [isViewingClient, setIsViewingClient] = useState(false);

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace('/auth');
    }
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

  if (isLoading) {
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
            Welcome, <span className="text-white font-medium">{user.nearAccountId}</span>
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

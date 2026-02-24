'use client';

import { useAuth } from '@/components/auth-provider';
import { redirect } from 'next/navigation';
import { useEffect } from 'react';
import { Sidebar } from '@/components/sidebar';
import { SyncStatus } from '@/components/sync-status';
import { Loader2 } from 'lucide-react';

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !user) {
      redirect('/');
    }
  }, [user, isLoading]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <div className="min-h-screen flex bg-gray-900">
      <Sidebar user={user} />
      <div className="flex-1 flex flex-col">
        {/* Header with sync status */}
        <header className="h-14 border-b border-gray-800 bg-gray-900/50 backdrop-blur px-6 flex items-center justify-between">
          <div className="text-sm text-gray-400">
            Welcome, <span className="text-white font-medium">{user.nearAccountId}</span>
          </div>
          <SyncStatus />
        </header>
        
        {/* Main content */}
        <main className="flex-1 p-6 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}

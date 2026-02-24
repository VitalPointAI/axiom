'use client';

import { useAuth } from '@/components/auth-provider';
import { redirect } from 'next/navigation';
import { useEffect } from 'react';
import { Sidebar } from '@/components/sidebar';
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
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return (
    <div className="min-h-screen flex">
      <Sidebar user={user} />
      <main className="flex-1 p-8 bg-slate-50">
        {children}
      </main>
    </div>
  );
}

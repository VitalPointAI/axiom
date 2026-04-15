'use client';

import { AuthProvider, useAuth } from '@/components/auth-provider';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { Loader2 } from 'lucide-react';

function SettingsLayoutInner({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace('/auth');
    }
  }, [user, isLoading, router]);

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
    <div className="min-h-screen bg-gray-900 p-4">
      <div className="max-w-3xl mx-auto py-8 space-y-6">
        <nav className="flex items-center gap-2 text-sm text-gray-400">
          <a href="/dashboard" className="hover:text-white transition-colors">
            Dashboard
          </a>
          <span>/</span>
          <span className="text-white">Settings</span>
        </nav>
        {children}
      </div>
    </div>
  );
}

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthProvider>
      <SettingsLayoutInner>{children}</SettingsLayoutInner>
    </AuthProvider>
  );
}

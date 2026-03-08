'use client';

import { useAuth } from './auth-provider';
import { Loader2, Wallet } from 'lucide-react';
import Link from 'next/link';

export function SignInButton() {
  const { user, isLoading, signOut } = useAuth();

  if (isLoading) {
    return (
      <button
        disabled
        className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-slate-100 text-slate-400 rounded-lg"
      >
        <Loader2 className="w-5 h-5 animate-spin" />
        Loading...
      </button>
    );
  }

  if (user) {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg border border-green-200">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-green-500 flex items-center justify-center">
              <Wallet className="w-4 h-4 text-white" />
            </div>
            <div>
              <p className="text-sm font-medium text-green-800">Connected</p>
              <p className="text-xs text-green-600 font-mono truncate max-w-[200px]">
                {user.codename || user.nearAccountId}
              </p>
            </div>
          </div>
        </div>
        <button
          onClick={signOut}
          className="w-full px-4 py-2 text-sm text-slate-600 hover:text-slate-800 hover:bg-slate-100 rounded-lg transition"
        >
          Sign Out
        </button>
      </div>
    );
  }

  return (
    <Link
      href="/auth"
      className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition font-medium"
    >
      <Wallet className="w-5 h-5" />
      Sign In
    </Link>
  );
}

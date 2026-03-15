'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { apiClient, ApiError } from '@/lib/api';

interface User {
  id: string;
  email?: string;
  near_account_id?: string;
  display_name?: string;
  is_admin?: boolean;
  nearAccountId: string;
  codename?: string;
  createdAt?: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  signOut: () => Promise<void>;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface SessionResponse {
  user: {
    user_id: number;
    near_account_id?: string;
    username?: string;
    email?: string;
    codename?: string;
    is_admin?: boolean;
  };
  expires_at: string;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  const checkSession = useCallback(async () => {
    try {
      const data = await apiClient.get<SessionResponse>('/auth/session');
      const u = data.user;
      setUser({
        id: String(u.user_id),
        email: u.email,
        near_account_id: u.near_account_id,
        display_name: u.codename || u.username,
        is_admin: u.is_admin,
        nearAccountId: u.near_account_id || u.email || u.codename || String(u.user_id),
        codename: u.codename,
        createdAt: undefined,
      });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setUser(null);
      } else {
        console.error('Session check failed:', err);
        setUser(null);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    setIsLoading(true);
    checkSession();
  }, [pathname, checkSession]);

  const signOut = async () => {
    try {
      await apiClient.post('/auth/logout');
      setUser(null);
      router.push('/auth');
    } catch (error) {
      console.error('Sign out failed:', error);
    }
  };

  const refreshSession = async () => {
    setIsLoading(true);
    await checkSession();
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        signOut,
        refreshSession,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/auth');
    }
  }, [user, isLoading, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-900"></div>
      </div>
    );
  }

  if (!user) {
    return null;
  }

  return <>{children}</>;
}

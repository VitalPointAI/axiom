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
  // Legacy compat: always set to best available identifier string
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
  id: string;
  email?: string;
  near_account_id?: string;
  display_name?: string;
  is_admin?: boolean;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  const checkSession = useCallback(async () => {
    try {
      const data = await apiClient.get<SessionResponse>('/auth/session');
      setUser({
        id: data.id,
        email: data.email,
        near_account_id: data.near_account_id,
        display_name: data.display_name,
        is_admin: data.is_admin,
        // Legacy compat fields
        nearAccountId: data.near_account_id || data.email || data.display_name || data.id,
        codename: data.display_name,
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

  // Check session on mount and when pathname changes (e.g., after login redirect)
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

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
  username?: string;
  authMethod?: string;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  signOut: () => Promise<void>;
  refreshSession: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// near-phantom-auth session response format
interface SessionInfo {
  authenticated: boolean;
  codename?: string;
  username?: string;
  nearAccountId?: string;
  email?: string;
  expiresAt?: string;
  authMethod?: 'passkey' | 'oauth' | 'email';
  // Axiom-specific fields added by user bridge
  userId?: string;
  axiomUserId?: number;
  isAdmin?: boolean;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  const checkSession = useCallback(async () => {
    try {
      const data = await apiClient.get<SessionInfo>('/auth/session');
      if (data.authenticated) {
        const id = data.userId || data.codename || data.nearAccountId || 'unknown';
        setUser({
          id,
          email: data.email,
          near_account_id: data.nearAccountId,
          display_name: data.codename || data.username,
          is_admin: data.isAdmin,
          nearAccountId: data.nearAccountId || data.email || data.codename || id,
          codename: data.codename,
          username: data.username,
          authMethod: data.authMethod,
        });
      } else {
        setUser(null);
      }
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
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

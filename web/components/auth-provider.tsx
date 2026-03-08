'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';

interface User {
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

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [retryCount, setRetryCount] = useState(0);
  const router = useRouter();

  const checkSession = useCallback(async (retry = false) => {
    try {
      const response = await fetch('/api/phantom-auth/session', {
        credentials: 'include',
        cache: 'no-store',
      });
      if (response.ok) {
        const data = await response.json();
        if (data.authenticated) {
          setUser({
            nearAccountId: data.nearAccountId,
            codename: data.codename,
            createdAt: data.createdAt,
          });
          setIsLoading(false);
          return;
        }
      }
      
      // If not authenticated and we haven't retried, wait and retry once
      // This handles cookie propagation timing on mobile
      if (retry && retryCount < 2) {
        setRetryCount(prev => prev + 1);
        await new Promise(resolve => setTimeout(resolve, 500));
        return checkSession(true);
      }
      
      setUser(null);
    } catch (error) {
      console.error('Session check failed:', error);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, [retryCount]);

  useEffect(() => {
    // Small delay on initial load to allow cookies to be set
    const timer = setTimeout(() => {
      checkSession(true);
    }, 100);
    return () => clearTimeout(timer);
  }, [checkSession]);

  const signOut = async () => {
    try {
      await fetch('/api/phantom-auth/logout', { 
        method: 'POST',
        credentials: 'include',
      });
      setUser(null);
      router.push('/auth');
    } catch (error) {
      console.error('Sign out failed:', error);
    }
  };

  const refreshSession = async () => {
    setIsLoading(true);
    await checkSession(false);
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

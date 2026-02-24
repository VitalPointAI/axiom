'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

interface User {
  nearAccountId: string;
  createdAt: Date;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  signIn: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Check for existing session on mount
  useEffect(() => {
    checkSession();
  }, []);

  const checkSession = async () => {
    try {
      const response = await fetch('/api/auth/session');
      if (response.ok) {
        const data = await response.json();
        if (data.user) {
          setUser({
            nearAccountId: data.user.nearAccountId,
            createdAt: new Date(data.user.createdAt),
          });
        }
      }
    } catch (error) {
      console.error('Session check failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const signIn = useCallback(async () => {
    try {
      setIsLoading(true);
      
      // For now, prompt for NEAR account ID
      // In production, this would use near-phantom-auth or wallet-selector
      const nearAccountId = prompt('Enter your NEAR account ID (e.g., yourname.near):');
      
      if (!nearAccountId) {
        throw new Error('No account ID provided');
      }

      // Validate format
      if (!nearAccountId.endsWith('.near') && !nearAccountId.includes('.')) {
        throw new Error('Invalid NEAR account ID format');
      }

      // Create/update user in our database
      const response = await fetch('/api/auth/signin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nearAccountId }),
      });

      if (response.ok) {
        const data = await response.json();
        setUser({
          nearAccountId: data.user.nearAccountId,
          createdAt: new Date(data.user.createdAt),
        });
      } else {
        throw new Error('Sign in failed');
      }
    } catch (error) {
      console.error('Sign in failed:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const signOut = useCallback(async () => {
    try {
      await fetch('/api/auth/signout', { method: 'POST' });
      setUser(null);
    } catch (error) {
      console.error('Sign out failed:', error);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, signIn, signOut }}>
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

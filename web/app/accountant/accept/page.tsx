'use client';

import { Suspense } from 'react';
import { useEffect, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import { useAuth } from '@/components/auth-provider';
import { CheckCircle, XCircle, Shield, ShieldCheck, Loader2, UserPlus } from 'lucide-react';

interface InviteInfo {
  valid: boolean;
  email: string;
  permissionLevel: 'read' | 'readwrite';
  clientName: string;
  message: string | null;
  expiresAt: string;
}

function AcceptInviteContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const { user } = useAuth();
  
  const [loading, setLoading] = useState(true);
  const [inviteInfo, setInviteInfo] = useState<InviteInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [accepting, setAccepting] = useState(false);
  const [accepted, setAccepted] = useState(false);

  const token = searchParams.get('token');

  useEffect(() => {
    if (!token) {
      setError('No invitation token provided');
      setLoading(false);
      return;
    }

    fetch(`/api/accountant/accept?token=${token}`)
      .then(res => res.json())
      .then(data => {
        if (data.error) {
          setError(data.error);
        } else {
          setInviteInfo(data);
        }
      })
      .catch(() => setError('Failed to verify invitation'))
      .finally(() => setLoading(false));
  }, [token]);

  const acceptInvite = async () => {
    if (!token) return;
    
    setAccepting(true);
    try {
      const res = await fetch('/api/accountant/accept', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token })
      });
      
      const data = await res.json();
      
      if (res.ok) {
        setAccepted(true);
        setTimeout(() => {
          router.push('/dashboard');
        }, 2000);
      } else {
        setError(data.error || 'Failed to accept invitation');
      }
    } catch {
      setError('Failed to accept invitation');
    } finally {
      setAccepting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
          <p className="mt-2 text-slate-500">Verifying invitation...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full text-center">
          <XCircle className="w-16 h-16 text-red-500 mx-auto" />
          <h1 className="text-xl font-bold mt-4">Invalid Invitation</h1>
          <p className="text-slate-500 mt-2">{error}</p>
          <button 
            onClick={() => router.push('/')}
            className="mt-6 px-4 py-2 bg-slate-100 rounded-lg hover:bg-slate-200 transition"
          >
            Go to Homepage
          </button>
        </div>
      </div>
    );
  }

  if (accepted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full text-center">
          <CheckCircle className="w-16 h-16 text-green-500 mx-auto" />
          <h1 className="text-xl font-bold mt-4">Invitation Accepted!</h1>
          <p className="text-slate-500 mt-2">
            You now have access to {inviteInfo?.clientName}'s tax reports.
          </p>
          <p className="text-sm text-slate-400 mt-4">Redirecting to dashboard...</p>
        </div>
      </div>
    );
  }

  if (!inviteInfo) {
    return null;
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
      <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
        <div className="text-center">
          <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mx-auto">
            <UserPlus className="w-8 h-8 text-blue-600" />
          </div>
          
          <h1 className="text-2xl font-bold mt-4">You're Invited</h1>
          
          <p className="text-slate-500 mt-2">
            <strong>{inviteInfo.clientName}</strong> has invited you to access their 
            NearTax account as their accountant.
          </p>
        </div>

        {inviteInfo.message && (
          <div className="mt-6 p-4 bg-slate-50 rounded-lg">
            <p className="text-sm text-slate-600 italic">"{inviteInfo.message}"</p>
          </div>
        )}

        <div className="mt-6 p-4 border rounded-lg">
          <div className="flex items-center gap-3">
            {inviteInfo.permissionLevel === 'read' ? (
              <Shield className="w-6 h-6 text-slate-500" />
            ) : (
              <ShieldCheck className="w-6 h-6 text-green-500" />
            )}
            <div>
              <p className="font-medium">
                {inviteInfo.permissionLevel === 'read' ? 'Read Only Access' : 'Read & Write Access'}
              </p>
              <p className="text-sm text-slate-500">
                {inviteInfo.permissionLevel === 'read'
                  ? 'You can view reports and download exports'
                  : 'You can view, edit categories, and add notes'}
              </p>
            </div>
          </div>
        </div>

        <div className="mt-6 text-sm text-slate-500">
          <p>Invitation sent to: <strong>{inviteInfo.email}</strong></p>
          <p>Expires: {new Date(inviteInfo.expiresAt).toLocaleDateString()}</p>
        </div>

        {!user ? (
          <div className="mt-6 space-y-3">
            <p className="text-sm text-amber-600 bg-amber-50 p-3 rounded-lg">
              You need to sign in or create an account to accept this invitation.
            </p>
            <button
              onClick={() => router.push(`/auth?redirect=/accountant/accept?token=${token}`)}
              className="w-full py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium"
            >
              Sign In / Create Account
            </button>
          </div>
        ) : (
          <div className="mt-6 space-y-3">
            <p className="text-sm text-green-600 bg-green-50 p-3 rounded-lg">
              Signed in as <strong>{user.codename || user.nearAccountId}</strong>
            </p>
            <button
              onClick={acceptInvite}
              disabled={accepting}
              className="w-full py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 transition font-medium flex items-center justify-center gap-2"
            >
              {accepting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Accepting...
                </>
              ) : (
                <>
                  <CheckCircle className="w-4 h-4" />
                  Accept Invitation
                </>
              )}
            </button>
            <button
              onClick={() => router.push('/')}
              className="w-full py-2 text-slate-500 hover:text-slate-700 transition"
            >
              Decline
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function AcceptInvitePage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
          <p className="mt-2 text-slate-500">Loading...</p>
        </div>
      </div>
    }>
      <AcceptInviteContent />
    </Suspense>
  );
}

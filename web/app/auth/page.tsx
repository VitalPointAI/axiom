'use client';

import { AnonAuthProvider, useAnonAuth } from '@vitalpoint/near-phantom-auth/client';
import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

type AuthMode = 'signin' | 'signup';
type SignupMethod = 'passkey' | 'google' | 'email';

function AuthContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const {
    isLoading,
    isAuthenticated,
    webAuthnSupported,
    platformAuthAvailable,
    oauthProviders,
    register,
    login,
    checkUsername,
    startOAuth,
    sendMagicLink,
    verifyMagicLink,
    error,
    clearError,
  } = useAnonAuth();

  const [mode, setMode] = useState<AuthMode>('signin');
  const [signupMethod, setSignupMethod] = useState<SignupMethod | null>(null);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [usernameStatus, setUsernameStatus] = useState<'idle' | 'checking' | 'available' | 'taken'>('idle');
  const [usernameSuggestion, setUsernameSuggestion] = useState<string | null>(null);
  const [emailSent, setEmailSent] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Auto-redirect to dashboard if already authenticated
  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.push('/dashboard');
    }
  }, [isLoading, isAuthenticated, router]);

  // Handle magic link token from URL
  useEffect(() => {
    const token = searchParams.get('token');
    if (token) {
      verifyMagicLink(token);
    }
  }, [searchParams, verifyMagicLink]);

  // Debounced username check
  useEffect(() => {
    if (!username || username.length < 3) {
      setUsernameStatus('idle');
      return;
    }

    const timer = setTimeout(async () => {
      setUsernameStatus('checking');
      const result = await checkUsername(username);
      setUsernameStatus(result.available ? 'available' : 'taken');
      setUsernameSuggestion(result.suggestion || null);
    }, 500);

    return () => clearTimeout(timer);
  }, [username, checkUsername]);

  const handlePasskeySignup = async () => {
    if (usernameStatus !== 'available' && username.length >= 3) {
      return;
    }
    setIsSubmitting(true);
    try {
      await register(username || undefined);
      router.push('/dashboard');
    } catch (e) {
      console.error('Registration failed:', e);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePasskeyLogin = async () => {
    setIsSubmitting(true);
    try {
      await login();
      router.push('/dashboard');
    } catch (e) {
      console.error('Login failed:', e);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleGoogleSignup = async () => {
    await startOAuth('google');
  };

  const handleEmailSignup = async () => {
    if (!email) return;
    setIsSubmitting(true);
    try {
      await sendMagicLink(email);
      setEmailSent(true);
    } catch (e) {
      console.error('Failed to send magic link:', e);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Show loading while checking auth or redirecting
  if (isLoading || isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500 mx-auto"></div>
          <p className="mt-4 text-gray-400">
            {isAuthenticated ? 'Redirecting...' : 'Loading...'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-900 p-4">
      <div className="bg-gray-800 rounded-lg p-8 max-w-md w-full">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">NearTax</h1>
          <p className="text-gray-400">Crypto Tax Tracking for NEAR</p>
        </div>

        {error && (
          <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 mb-6">
            <div className="flex justify-between items-start">
              <p className="text-red-400 text-sm">{error}</p>
              <button onClick={clearError} className="text-red-400 hover:text-red-300">✕</button>
            </div>
          </div>
        )}

        {/* Mode Tabs */}
        <div className="flex mb-6 bg-gray-700/50 rounded-lg p-1">
          <button
            onClick={() => { setMode('signin'); setSignupMethod(null); }}
            className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition ${
              mode === 'signin' ? 'bg-gray-600 text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            Sign In
          </button>
          <button
            onClick={() => setMode('signup')}
            className={`flex-1 py-2 px-4 rounded-md text-sm font-medium transition ${
              mode === 'signup' ? 'bg-gray-600 text-white' : 'text-gray-400 hover:text-white'
            }`}
          >
            Sign Up
          </button>
        </div>

        {mode === 'signin' ? (
          /* Sign In Mode */
          <div className="space-y-4">
            {webAuthnSupported && (
              <button
                onClick={handlePasskeyLogin}
                disabled={isSubmitting}
                className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                {isSubmitting ? (
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                ) : (
                  <span className="text-xl">🔑</span>
                )}
                Sign In with Passkey
              </button>
            )}

            {oauthProviders.some(p => p.name === 'google') && (
              <button
                onClick={handleGoogleSignup}
                className="w-full bg-white hover:bg-gray-100 text-gray-800 font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                Continue with Google
              </button>
            )}
          </div>
        ) : signupMethod === null ? (
          /* Sign Up Method Selection */
          <div className="space-y-4">
            <p className="text-gray-400 text-sm text-center mb-4">Choose how to create your account</p>
            
            {webAuthnSupported && (
              <button
                onClick={() => setSignupMethod('passkey')}
                className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                <span className="text-xl">🔐</span>
                Passkey (Face ID / Touch ID)
              </button>
            )}

            {oauthProviders.some(p => p.name === 'google') && (
              <button
                onClick={handleGoogleSignup}
                className="w-full bg-white hover:bg-gray-100 text-gray-800 font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24">
                  <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                  <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                </svg>
                Continue with Google
              </button>
            )}

            <button
              onClick={() => setSignupMethod('email')}
              className="w-full bg-gray-700 hover:bg-gray-600 text-white font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              <span className="text-xl">✉️</span>
              Email Magic Link
            </button>
          </div>
        ) : signupMethod === 'passkey' ? (
          /* Passkey Signup with Username */
          <div className="space-y-4">
            <button
              onClick={() => setSignupMethod(null)}
              className="text-gray-400 hover:text-white text-sm flex items-center gap-1"
            >
              ← Back
            </button>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Choose a username (optional)
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, ''))}
                placeholder="myusername"
                className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-emerald-500"
                maxLength={20}
              />
              <div className="mt-2 text-sm">
                {usernameStatus === 'checking' && (
                  <span className="text-gray-400">Checking availability...</span>
                )}
                {usernameStatus === 'available' && (
                  <span className="text-emerald-400">✓ Username available</span>
                )}
                {usernameStatus === 'taken' && (
                  <span className="text-red-400">
                    ✗ Username taken
                    {usernameSuggestion && (
                      <button
                        onClick={() => setUsername(usernameSuggestion)}
                        className="ml-2 text-blue-400 hover:underline"
                      >
                        Try {usernameSuggestion}?
                      </button>
                    )}
                  </span>
                )}
              </div>
            </div>

            <button
              onClick={handlePasskeySignup}
              disabled={isSubmitting || (username.length >= 3 && usernameStatus !== 'available')}
              className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
              ) : (
                <span className="text-xl">🔐</span>
              )}
              Create Account with Passkey
            </button>

            <p className="text-xs text-gray-500 text-center">
              Uses Face ID, Touch ID, or Windows Hello
            </p>
          </div>
        ) : signupMethod === 'email' ? (
          /* Email Magic Link Signup */
          <div className="space-y-4">
            <button
              onClick={() => { setSignupMethod(null); setEmailSent(false); }}
              className="text-gray-400 hover:text-white text-sm flex items-center gap-1"
            >
              ← Back
            </button>

            {emailSent ? (
              <div className="text-center py-8">
                <div className="text-6xl mb-4">📬</div>
                <h3 className="text-xl font-semibold text-white mb-2">Check your email</h3>
                <p className="text-gray-400">
                  We sent a magic link to <span className="text-white">{email}</span>
                </p>
                <button
                  onClick={() => setEmailSent(false)}
                  className="mt-4 text-blue-400 hover:underline text-sm"
                >
                  Use a different email
                </button>
              </div>
            ) : (
              <>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-2">
                    Email address
                  </label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-emerald-500"
                  />
                </div>

                <button
                  onClick={handleEmailSignup}
                  disabled={isSubmitting || !email}
                  className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
                >
                  {isSubmitting ? (
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                  ) : (
                    <span className="text-xl">✉️</span>
                  )}
                  Send Magic Link
                </button>
              </>
            )}
          </div>
        ) : null}

        {platformAuthAvailable && mode === 'signup' && signupMethod === null && (
          <p className="text-center text-sm text-emerald-400 mt-4">
            ✓ Biometric authentication available
          </p>
        )}
      </div>
    </div>
  );
}

function AuthPageInner() {
  return (
    <AnonAuthProvider apiUrl="/api/phantom-auth">
      <AuthContent />
    </AnonAuthProvider>
  );
}

export default function AuthPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500"></div>
      </div>
    }>
      <AuthPageInner />
    </Suspense>
  );
}

'use client';

import { useState, useEffect, useRef, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  AnonAuthProvider,
  useAnonAuth,
} from '@vitalpoint/near-phantom-auth/client';
import { NearConnector } from '@hot-labs/near-connect';
import { API_URL } from '@/lib/api';

type AuthView = 'signin' | 'signup' | 'signup-passkey' | 'signup-email' | 'recover' | 'recover-wallet' | 'recover-password';

function AuthContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const {
    isLoading: authLoading,
    isAuthenticated,
    webAuthnSupported,
    error: authError,
    clearError,
    register,
    login,
    recovery,
    sendMagicLink,
    verifyMagicLink,
    startOAuth,
  } = useAnonAuth();

  const [view, setView] = useState<AuthView>('signin');
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [emailSent, setEmailSent] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Recovery state
  const [recoveryCid, setRecoveryCid] = useState('');
  const [recoveryPassword, setRecoveryPassword] = useState('');
  const connectorRef = useRef<NearConnector | null>(null);

  // Redirect if authenticated
  useEffect(() => {
    if (isAuthenticated && !authLoading) {
      router.push('/dashboard');
    }
  }, [isAuthenticated, authLoading, router]);

  // Handle magic link token from URL
  useEffect(() => {
    const token = searchParams.get('token');
    if (token) {
      handleMagicLinkVerify(token);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Sync auth errors
  useEffect(() => {
    if (authError) setError(authError);
  }, [authError]);

  const resetError = () => {
    setError(null);
    clearError();
  };

  // --- Passkey Registration ---
  const handlePasskeySignup = async () => {
    setIsSubmitting(true);
    resetError();
    try {
      await register(username || undefined);
      router.push('/dashboard');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Registration failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  // --- Passkey Login ---
  const handlePasskeyLogin = async () => {
    setIsSubmitting(true);
    resetError();
    try {
      await login();
      router.push('/dashboard');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Login failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  // --- Google OAuth ---
  const handleGoogleAuth = async () => {
    resetError();
    try {
      await startOAuth('google');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start Google sign-in');
    }
  };

  // --- Email Magic Link ---
  const handleEmailSignup = async () => {
    if (!email) return;
    setIsSubmitting(true);
    resetError();
    try {
      await sendMagicLink(email);
      setEmailSent(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to send magic link');
    } finally {
      setIsSubmitting(false);
    }
  };

  // --- Magic Link Verification ---
  const handleMagicLinkVerify = async (token: string) => {
    try {
      await verifyMagicLink(token);
      router.push('/dashboard');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Magic link is invalid or expired.');
    }
  };

  // --- Recovery: Password + IPFS ---
  const handlePasswordRecovery = async () => {
    if (!recoveryCid || !recoveryPassword) return;
    setIsSubmitting(true);
    resetError();
    try {
      await recovery.recoverWithPassword(recoveryCid, recoveryPassword);
      router.push('/dashboard');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Recovery failed. Check your CID and password.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // --- Recovery: Wallet ---
  const handleWalletRecovery = async () => {
    setIsSubmitting(true);
    resetError();
    try {
      // Create a nonce (32 bytes as base64)
      const nonceArray = new Uint8Array(32);
      crypto.getRandomValues(nonceArray);
      const nonce = Buffer.from(nonceArray);

      const connector = new NearConnector({
        features: { signMessage: true },
      });
      connectorRef.current = connector;

      // Connect wallet with message signing for recovery proof
      const recoveryMessage = `Axiom account recovery: ${Date.now()}`;

      // Set up the sign-in handler before connecting
      const walletPromise = new Promise<{ accountId: string; signature: string; publicKey: string }>((resolve, reject) => {
        connector.on('wallet:signInAndSignMessage', async (event) => {
          const account = event.accounts[0];
          if (account?.signedMessage) {
            resolve({
              accountId: account.accountId,
              signature: account.signedMessage.signature,
              publicKey: account.signedMessage.publicKey,
            });
          } else {
            reject(new Error('Wallet did not return a signed message'));
          }
        });

        connector.on('wallet:signIn', async (event) => {
          if (event.source !== 'signInAndSignMessage') {
            reject(new Error('Wallet does not support message signing. Please use a wallet that supports signMessage.'));
          }
        });
      });

      // Trigger the wallet connection modal with message signing
      await connector.connect({
        signMessageParams: {
          message: recoveryMessage,
          recipient: 'Axiom',
          nonce,
        },
      });

      // Wait for the wallet to sign
      const { accountId, signature, publicKey } = await walletPromise;

      // Use the signed message to recover the account
      await recovery.recoverWithWallet(
        async () => ({ signature, publicKey }),
        accountId,
      );

      router.push('/dashboard');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Wallet recovery failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-900">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500"></div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-900 p-4">
      <div className="bg-gray-800 rounded-lg p-8 max-w-md w-full">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">Axiom</h1>
          <p className="text-gray-400">Crypto Tax Tracking</p>
        </div>

        {error && (
          <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 mb-6">
            <div className="flex justify-between items-start">
              <p className="text-red-400 text-sm">{error}</p>
              <button onClick={resetError} className="text-red-400 hover:text-red-300 ml-2">
                ✕
              </button>
            </div>
          </div>
        )}

        {/* --- Sign In --- */}
        {view === 'signin' && (
          <div className="space-y-4">
            <div className="flex mb-6 bg-gray-700/50 rounded-lg p-1">
              <button
                onClick={() => setView('signin')}
                className="flex-1 py-2 px-4 rounded-md text-sm font-medium bg-gray-600 text-white"
              >
                Sign In
              </button>
              <button
                onClick={() => setView('signup')}
                className="flex-1 py-2 px-4 rounded-md text-sm font-medium text-gray-400 hover:text-white transition"
              >
                Sign Up
              </button>
            </div>

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

            <button
              onClick={handleGoogleAuth}
              className="w-full bg-white hover:bg-gray-100 text-gray-800 font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              <GoogleIcon />
              Continue with Google
            </button>

            <div className="text-center pt-2">
              <button
                onClick={() => setView('recover')}
                className="text-emerald-400 hover:text-emerald-300 text-sm hover:underline"
              >
                Lost your passkey? Recover account
              </button>
            </div>
          </div>
        )}

        {/* --- Sign Up Method Selection --- */}
        {view === 'signup' && (
          <div className="space-y-4">
            <div className="flex mb-6 bg-gray-700/50 rounded-lg p-1">
              <button
                onClick={() => setView('signin')}
                className="flex-1 py-2 px-4 rounded-md text-sm font-medium text-gray-400 hover:text-white transition"
              >
                Sign In
              </button>
              <button
                onClick={() => setView('signup')}
                className="flex-1 py-2 px-4 rounded-md text-sm font-medium bg-gray-600 text-white"
              >
                Sign Up
              </button>
            </div>

            <p className="text-gray-400 text-sm text-center mb-4">Choose how to create your account</p>

            {webAuthnSupported && (
              <button
                onClick={() => setView('signup-passkey')}
                className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                <span className="text-xl">🔐</span>
                Passkey (Face ID / Touch ID)
              </button>
            )}

            <button
              onClick={handleGoogleAuth}
              className="w-full bg-white hover:bg-gray-100 text-gray-800 font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              <GoogleIcon />
              Continue with Google
            </button>

            <button
              onClick={() => setView('signup-email')}
              className="w-full bg-gray-700 hover:bg-gray-600 text-white font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              <span className="text-xl">✉️</span>
              Email Magic Link
            </button>
          </div>
        )}

        {/* --- Passkey Signup with Username --- */}
        {view === 'signup-passkey' && (
          <div className="space-y-4">
            <button onClick={() => setView('signup')} className="text-gray-400 hover:text-white text-sm flex items-center gap-1">
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
            </div>

            <button
              onClick={handlePasskeySignup}
              disabled={isSubmitting}
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
        )}

        {/* --- Email Magic Link --- */}
        {view === 'signup-email' && (
          <div className="space-y-4">
            <button
              onClick={() => { setView('signup'); setEmailSent(false); }}
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
        )}

        {/* --- Account Recovery Selection --- */}
        {view === 'recover' && (
          <div className="space-y-4">
            <button onClick={() => setView('signin')} className="text-gray-400 hover:text-white text-sm flex items-center gap-1">
              ← Back to Sign In
            </button>

            <h2 className="text-xl font-semibold text-white text-center">Recover Your Account</h2>
            <p className="text-gray-400 text-sm text-center mb-4">
              Choose a recovery method to regain access
            </p>

            <button
              onClick={() => setView('signup-email')}
              className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              <span className="text-xl">✉️</span>
              Recover via Email
            </button>

            <button
              onClick={handleGoogleAuth}
              className="w-full bg-white hover:bg-gray-100 text-gray-800 font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              <GoogleIcon />
              Recover via Google
            </button>

            <button
              onClick={() => setView('recover-wallet')}
              className="w-full bg-gray-700 hover:bg-gray-600 text-white font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              <span className="text-xl">👛</span>
              Recover via NEAR Wallet
            </button>

            <button
              onClick={() => setView('recover-password')}
              className="w-full bg-gray-700 hover:bg-gray-600 text-white font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              <span className="text-xl">🔐</span>
              Recover via Backup Password
            </button>
          </div>
        )}

        {/* --- Wallet Recovery --- */}
        {view === 'recover-wallet' && (
          <div className="space-y-4">
            <button onClick={() => setView('recover')} className="text-gray-400 hover:text-white text-sm flex items-center gap-1">
              ← Back
            </button>

            <h2 className="text-xl font-semibold text-white text-center">Wallet Recovery</h2>
            <p className="text-gray-400 text-sm text-center mb-4">
              Sign a message with your linked NEAR wallet to prove ownership and create a new passkey.
            </p>

            <button
              onClick={handleWalletRecovery}
              disabled={isSubmitting}
              className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
              ) : (
                <span className="text-xl">👛</span>
              )}
              Connect NEAR Wallet
            </button>

            <p className="text-xs text-gray-500 text-center">
              You must have previously linked a NEAR wallet to your account in Settings.
            </p>
          </div>
        )}

        {/* --- Password + IPFS Recovery --- */}
        {view === 'recover-password' && (
          <div className="space-y-4">
            <button onClick={() => setView('recover')} className="text-gray-400 hover:text-white text-sm flex items-center gap-1">
              ← Back
            </button>

            <h2 className="text-xl font-semibold text-white text-center">Backup Password Recovery</h2>
            <p className="text-gray-400 text-sm text-center mb-4">
              Enter your backup CID and password to restore your account.
            </p>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Backup CID</label>
              <input
                type="text"
                value={recoveryCid}
                onChange={(e) => setRecoveryCid(e.target.value.trim())}
                placeholder="QmXyz..."
                className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-emerald-500 font-mono text-sm"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">Backup Password</label>
              <input
                type="password"
                value={recoveryPassword}
                onChange={(e) => setRecoveryPassword(e.target.value)}
                placeholder="Enter your backup password"
                className="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:border-emerald-500"
              />
            </div>

            <button
              onClick={handlePasswordRecovery}
              disabled={isSubmitting || !recoveryCid || !recoveryPassword}
              className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white font-medium py-4 px-4 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              {isSubmitting ? (
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
              ) : (
                <span className="text-xl">🔐</span>
              )}
              Recover Account
            </button>

            <p className="text-xs text-gray-500 text-center">
              You should have saved your CID and password when you set up account backup in Settings.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg className="w-5 h-5" viewBox="0 0 24 24">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  );
}

export default function AuthPage() {
  return (
    <AnonAuthProvider apiUrl={`${API_URL}/auth`}>
      <Suspense
        fallback={
          <div className="min-h-screen flex items-center justify-center bg-gray-900">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500"></div>
          </div>
        }
      >
        <AuthContent />
      </Suspense>
    </AnonAuthProvider>
  );
}

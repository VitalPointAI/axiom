'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Shield, ChevronDown, ChevronUp, ArrowRight } from 'lucide-react';

export default function ReturningUserPage() {
  const router = useRouter();
  const [expanded, setExpanded] = useState(false);

  function handleContinue() {
    // Route to the wallet-entry step of onboarding, tagging as returning
    router.push('/onboarding?step=wallets&returning=1');
  }

  return (
    <div className="space-y-6">
      {/* Header with icon */}
      <div className="text-center space-y-3">
        <div className="flex justify-center">
          <div className="w-16 h-16 rounded-full bg-blue-900/40 border border-blue-700 flex items-center justify-center">
            <Shield className="w-8 h-8 text-blue-400" />
          </div>
        </div>
        <h1 className="text-2xl font-bold text-white">Welcome back to Axiom</h1>
        <p className="text-gray-400 max-w-md mx-auto">
          We upgraded to post-quantum encryption. Your account is safe, but your wallets
          need to be re-entered to restore access to your tax data.
        </p>
      </div>

      {/* What happened — expandable */}
      <div className="rounded-lg border border-gray-700 bg-gray-800">
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center justify-between p-4 text-left"
        >
          <span className="font-medium text-white text-sm">What happened?</span>
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          )}
        </button>

        {expanded && (
          <div className="px-4 pb-4 text-sm text-gray-300 leading-relaxed space-y-3 border-t border-gray-700 pt-4">
            <p>
              Axiom upgraded to <strong className="text-white">post-quantum (ML-KEM-768) encryption</strong>{' '}
              for all your stored data. Every piece of your financial information &mdash; transactions,
              balances, tax records &mdash; is now encrypted with a key that only you control.
            </p>
            <p>
              As part of this upgrade, all previously stored user data was cleared and will be
              re-indexed fresh. Your account credentials (passkey, linked wallets) were preserved.
            </p>
            <p>
              To restore your data, simply re-enter your wallet addresses below. Axiom will
              re-index them from the NEAR blockchain automatically.
            </p>
            <p className="text-xs text-gray-500">
              This is a one-time step. Future updates will not require re-entry.
            </p>
          </div>
        )}
      </div>

      {/* What you need to do */}
      <div className="rounded-lg border border-gray-700 bg-gray-800/50 p-4 space-y-2">
        <p className="text-sm font-medium text-white">What you need to do:</p>
        <ol className="space-y-1 text-sm text-gray-300 list-decimal list-inside">
          <li>Re-enter your NEAR wallet addresses</li>
          <li>Axiom will automatically re-index your transactions</li>
          <li>Your tax reports will be regenerated</li>
        </ol>
      </div>

      {/* CTA */}
      <div className="flex flex-col items-center gap-3">
        <button
          onClick={handleContinue}
          className="w-full flex items-center justify-center gap-2 py-3 px-6 bg-blue-600 hover:bg-blue-500 text-white font-medium rounded-lg transition-colors"
        >
          Continue to wallet setup
          <ArrowRight className="w-4 h-4" />
        </button>
        <p className="text-xs text-gray-500">
          This takes about 2 minutes once your wallets are entered.
        </p>
      </div>
    </div>
  );
}

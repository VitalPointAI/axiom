'use client';

import { Wallet, ChevronRight, ArrowRight, CheckCircle } from 'lucide-react';

interface WelcomeStepProps {
  onNext: () => void;
  onSkip: () => void;
}

export function WelcomeStep({ onNext, onSkip }: WelcomeStepProps) {
  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-8 space-y-6">
      {/* Icon + Title */}
      <div className="text-center space-y-3">
        <div className="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center mx-auto">
          <Wallet className="w-8 h-8 text-white" />
        </div>
        <h1 className="text-3xl font-bold text-white">Welcome to Axiom</h1>
        <p className="text-gray-400 text-lg max-w-md mx-auto">
          Accurate crypto tax reporting for Canadian users. We&apos;ll help you get everything set up.
        </p>
      </div>

      {/* What we'll do */}
      <div className="bg-gray-900 rounded-lg p-5 space-y-3">
        <h2 className="text-white font-semibold text-sm uppercase tracking-wide">Setup Process</h2>
        <ul className="space-y-2">
          {[
            'Add your crypto wallets (NEAR, ETH, Polygon, and more)',
            'Optionally import exchange transaction files (Coinbase, Crypto.com, Wealthsimple)',
            'Axiom automatically indexes, classifies, and calculates your cost basis',
            'Review your imported data and explore tax reports',
          ].map((item, i) => (
            <li key={i} className="flex items-start gap-3 text-sm text-gray-300">
              <CheckCircle className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* CTA */}
      <div className="space-y-3">
        <button
          onClick={onNext}
          className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg transition-colors"
        >
          Get Started
          <ArrowRight className="w-5 h-5" />
        </button>
        <button
          onClick={onSkip}
          className="w-full text-sm text-gray-400 hover:text-gray-300 transition-colors py-2"
        >
          I know what I&apos;m doing — skip to dashboard
          <ChevronRight className="w-4 h-4 inline ml-1" />
        </button>
      </div>
    </div>
  );
}

'use client';

import dynamic from 'next/dynamic';

// Disable SSR for the swap widget - uses browser APIs
const SwapWidget = dynamic(
  () => import('@/components/SwapWidget').then((mod) => mod.SwapWidget),
  { 
    ssr: false,
    loading: () => (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500" />
      </div>
    ),
  }
);

export default function SwapPage() {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-white">Swap</h1>
        <p className="text-gray-400 text-sm mt-1">
          Cross-chain token swaps powered by NEAR Intents
        </p>
      </div>
      
      <div className="max-w-lg">
        <SwapWidget />
      </div>
      
      <div className="mt-6 text-gray-500 text-xs">
        <p>Swaps are processed via Aurora Intents. 3% fee applies.</p>
        <a 
          href="https://aurora-labs.gitbook.io/intents-swap-widget/" 
          target="_blank" 
          rel="noopener noreferrer"
          className="text-blue-400 hover:underline"
        >
          Learn more
        </a>
      </div>
    </div>
  );
}

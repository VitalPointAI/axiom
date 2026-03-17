'use client';

import { useState, useEffect } from 'react';
import { Plus, X, ChevronRight, Info, Loader2, Wallet } from 'lucide-react';
import { apiClient, ApiError } from '@/lib/api';

interface WalletsStepProps {
  onNext: () => void;
  onSkip: () => void;
}

interface PendingWallet {
  id: string;
  chain: string;
  address: string;
}

const CHAINS = [
  { id: 'NEAR', name: 'NEAR Protocol', color: 'bg-green-500' },
  { id: 'ETH', name: 'Ethereum', color: 'bg-blue-500' },
  { id: 'Polygon', name: 'Polygon', color: 'bg-purple-500' },
  { id: 'Cronos', name: 'Cronos', color: 'bg-blue-400' },
  { id: 'Optimism', name: 'Optimism', color: 'bg-red-500' },
];

const CHAIN_HELP: Record<string, {
  format: string;
  whereToFind: string;
  whatsPulled: string;
  example: string;
}> = {
  NEAR: {
    format: 'yourname.near or 64-character hex string',
    whereToFind: 'NEAR wallet app → Copy Address',
    whatsPulled: 'All NEAR transactions, staking rewards, lockup vesting',
    example: 'vitalpointai.near',
  },
  ETH: {
    format: '0x followed by 40 hex characters',
    whereToFind: 'MetaMask → Account details → Copy address',
    whatsPulled: 'Token transfers, DeFi interactions, ETH transactions',
    example: '0x742d35Cc6641C4532DC3E4D5E5CF7e7 ...',
  },
  Polygon: {
    format: '0x followed by 40 hex characters',
    whereToFind: 'MetaMask → Account details → Copy address',
    whatsPulled: 'MATIC and token transfers, DeFi interactions',
    example: '0x742d35Cc6641C4532DC3E4D5E5CF7e7 ...',
  },
  Cronos: {
    format: '0x followed by 40 hex characters',
    whereToFind: 'MetaMask → Account details → Copy address',
    whatsPulled: 'CRO and token transfers, DeFi interactions',
    example: '0x742d35Cc6641C4532DC3E4D5E5CF7e7 ...',
  },
  Optimism: {
    format: '0x followed by 40 hex characters',
    whereToFind: 'MetaMask → Account details → Copy address',
    whatsPulled: 'ETH and token transfers on Optimism L2',
    example: '0x742d35Cc6641C4532DC3E4D5E5CF7e7 ...',
  },
};

interface ExistingWallet {
  id: number;
  account_id: string;
  chain: string;
}

export function WalletsStep({ onNext, onSkip }: WalletsStepProps) {
  const [selectedChain, setSelectedChain] = useState('NEAR');
  const [address, setAddress] = useState('');
  const [pendingWallets, setPendingWallets] = useState<PendingWallet[]>([]);
  const [existingWallets, setExistingWallets] = useState<ExistingWallet[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    apiClient
      .get<ExistingWallet[]>('/api/wallets')
      .then((data) => setExistingWallets(data || []))
      .catch(() => {});
  }, []);

  const handleAddWallet = () => {
    if (!address.trim()) return;
    const id = Math.random().toString(36).substring(2, 9);
    setPendingWallets((prev) => [...prev, { id, chain: selectedChain, address: address.trim() }]);
    setAddress('');
    setError('');
  };

  const handleRemoveWallet = (id: string) => {
    setPendingWallets((prev) => prev.filter((w) => w.id !== id));
  };

  const handleContinue = async () => {
    if (pendingWallets.length === 0 && existingWallets.length === 0) return;

    // If only existing wallets, skip straight to next step
    if (pendingWallets.length === 0) {
      onNext();
      return;
    }

    setSubmitting(true);
    setError('');

    // Submit wallets sequentially to avoid race conditions
    for (const wallet of pendingWallets) {
      try {
        await apiClient.post('/api/wallets', {
          account_id: wallet.address,
          chain: wallet.chain,
        });
      } catch (err) {
        if (err instanceof ApiError) {
          const body = err.body as Record<string, unknown>;
          setError(`Failed to add ${wallet.address}: ${String(body?.detail || 'Unknown error')}`);
        } else {
          setError(`Failed to add ${wallet.address}`);
        }
        setSubmitting(false);
        return;
      }
    }

    setSubmitting(false);
    onNext();
  };

  const chainInfo = CHAIN_HELP[selectedChain];
  const chainConfig = CHAINS.find((c) => c.id === selectedChain);

  const truncateAddress = (addr: string) => {
    if (addr.length <= 20) return addr;
    return `${addr.slice(0, 10)}...${addr.slice(-8)}`;
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 space-y-5">
      <div>
        <h2 className="text-xl font-bold text-white">Add Your Wallets</h2>
        <p className="text-gray-400 text-sm mt-1">
          {existingWallets.length > 0
            ? 'Your wallets from before are ready. Add more or continue to the next step.'
            : 'Add all wallets you want to track. You can add more later from the dashboard.'}
        </p>
      </div>

      {/* Chain + Address Input */}
      <div className="space-y-3">
        <div className="flex gap-2">
          <select
            value={selectedChain}
            onChange={(e) => setSelectedChain(e.target.value)}
            className="px-3 py-2 bg-gray-900 border border-gray-600 text-white rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 min-w-[140px]"
          >
            {CHAINS.map((chain) => (
              <option key={chain.id} value={chain.id}>
                {chain.name}
              </option>
            ))}
          </select>
          <input
            type="text"
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleAddWallet()}
            placeholder={selectedChain === 'NEAR' ? 'yourname.near or 64-char hex' : '0x...'}
            className="flex-1 px-3 py-2 bg-gray-900 border border-gray-600 text-white placeholder-gray-500 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
          <button
            onClick={handleAddWallet}
            disabled={!address.trim()}
            className="px-3 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded-lg transition-colors flex items-center gap-1"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>

        {/* Contextual help panel */}
        {chainInfo && (
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-4 space-y-2">
            <div className="flex items-center gap-2 text-blue-400 text-xs font-semibold uppercase tracking-wide">
              <Info className="w-3.5 h-3.5" />
              {chainConfig?.name} Help
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
              <div>
                <span className="text-gray-500">Format: </span>
                <span className="text-gray-300">{chainInfo.format}</span>
              </div>
              <div>
                <span className="text-gray-500">Where to find: </span>
                <span className="text-gray-300">{chainInfo.whereToFind}</span>
              </div>
              <div>
                <span className="text-gray-500">What&apos;s pulled: </span>
                <span className="text-gray-300">{chainInfo.whatsPulled}</span>
              </div>
              <div>
                <span className="text-gray-500">Example: </span>
                <code className="text-green-400 font-mono">{chainInfo.example}</code>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Existing wallets from previous attempt */}
      {existingWallets.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-gray-300">
            Your wallets ({existingWallets.length})
          </h3>
          <div className="space-y-2">
            {existingWallets.map((wallet) => {
              const chain = CHAINS.find((c) => c.id === wallet.chain);
              return (
                <div
                  key={wallet.id}
                  className="flex items-center bg-gray-900 border border-gray-700 rounded-lg px-3 py-2"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${chain?.color || 'bg-gray-500'}`} />
                    <span className="text-xs text-gray-400 font-medium">{wallet.chain}</span>
                    <code className="text-xs text-white font-mono">{truncateAddress(wallet.account_id)}</code>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Pending wallets list */}
      {pendingWallets.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-gray-300">
            {existingWallets.length > 0 ? 'New wallets' : 'Wallets to add'} ({pendingWallets.length})
          </h3>
          <div className="space-y-2">
            {pendingWallets.map((wallet) => {
              const chain = CHAINS.find((c) => c.id === wallet.chain);
              return (
                <div
                  key={wallet.id}
                  className="flex items-center justify-between bg-gray-900 border border-gray-700 rounded-lg px-3 py-2"
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-2 h-2 rounded-full ${chain?.color || 'bg-gray-500'}`} />
                    <span className="text-xs text-gray-400 font-medium">{wallet.chain}</span>
                    <code className="text-xs text-white font-mono">{truncateAddress(wallet.address)}</code>
                  </div>
                  <button
                    onClick={() => handleRemoveWallet(wallet.id)}
                    className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Wallet icon for empty state */}
      {pendingWallets.length === 0 && existingWallets.length === 0 && (
        <div className="text-center py-4 text-gray-600">
          <Wallet className="w-8 h-8 mx-auto mb-2" />
          <p className="text-sm">Add at least one wallet to continue</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-900/30 border border-red-700 text-red-300 text-sm rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="space-y-2 pt-2">
        <button
          onClick={handleContinue}
          disabled={(pendingWallets.length === 0 && existingWallets.length === 0) || submitting}
          className="w-full flex items-center justify-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-semibold rounded-lg transition-colors"
        >
          {submitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Adding wallets...
            </>
          ) : (
            <>
              Continue
              <ChevronRight className="w-4 h-4" />
            </>
          )}
        </button>
        <button
          onClick={onSkip}
          className="w-full text-sm text-gray-400 hover:text-gray-300 transition-colors py-2"
        >
          Skip to dashboard
          <ChevronRight className="w-3 h-3 inline ml-1" />
        </button>
      </div>
    </div>
  );
}

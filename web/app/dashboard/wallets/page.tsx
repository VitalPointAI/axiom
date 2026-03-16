'use client';

import { useState, useEffect } from 'react';
import { OnboardingBanner } from '@/components/onboarding-banner';
import {
  Wallet,
  Plus,
  RefreshCw,
  Trash2,
  CheckCircle,
  Clock,
  AlertCircle,
  X,
} from 'lucide-react';
import { apiClient, ApiError } from '@/lib/api';
import { SyncStatus } from '@/components/sync-status';

interface WalletData {
  id: number;
  account_id: string;
  chain: string;
  sync_status: string;
  last_synced_at: string | null;
  created_at: string;
}

interface WalletsResponse {
  wallets: WalletData[];
}

const CHAINS = [
  { id: 'NEAR', name: 'NEAR Protocol', color: 'bg-green-500' },
  { id: 'ETH', name: 'Ethereum', color: 'bg-blue-500' },
  { id: 'Polygon', name: 'Polygon', color: 'bg-purple-500' },
  { id: 'Cronos', name: 'Cronos', color: 'bg-blue-400' },
  { id: 'Optimism', name: 'Optimism', color: 'bg-red-500' },
];

export default function WalletsPage() {
  const [wallets, setWallets] = useState<WalletData[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [syncing, setSyncing] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  const fetchWallets = async () => {
    try {
      const data = await apiClient.get<WalletsResponse>('/api/wallets');
      setWallets(data.wallets || []);
    } catch (error) {
      console.error('Failed to fetch wallets:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWallets();
  }, []);

  const handleSync = async (walletId: number) => {
    setSyncing(walletId);
    try {
      await apiClient.post(`/api/wallets/${walletId}/resync`);
      await fetchWallets();
    } catch (error) {
      console.error('Sync failed:', error);
    } finally {
      setSyncing(null);
    }
  };

  const handleDelete = async (walletId: number) => {
    if (
      !confirm(
        'Are you sure you want to delete this wallet? All associated transactions will be removed.'
      )
    ) {
      return;
    }

    setDeleting(walletId);
    try {
      await apiClient.delete(`/api/wallets/${walletId}`);
      await fetchWallets();
    } catch (error) {
      console.error('Delete failed:', error);
    } finally {
      setDeleting(null);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'complete':
      case 'synced':
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'syncing':
      case 'in_progress':
        return <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" />;
      case 'error':
        return <AlertCircle className="w-4 h-4 text-red-500" />;
      default:
        return <Clock className="w-4 h-4 text-yellow-500" />;
    }
  };

  const getChainInfo = (chainId: string) => {
    return CHAINS.find((c) => c.id === chainId) || { id: chainId, name: chainId, color: 'bg-gray-500' };
  };

  return (
    <div className="space-y-6">
      <OnboardingBanner
        bannerKey="wallets_page"
        title="Wallet Management"
        description="Add your crypto wallets and exchange accounts here. After adding a wallet, Axiom automatically indexes all transactions, classifies them for tax purposes, calculates cost basis, and verifies balances against on-chain data. The sync status shows where each wallet is in the pipeline."
      />
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Wallets</h1>
          <p className="text-slate-500">Manage your crypto wallets</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition"
        >
          <Plus className="w-4 h-4" />
          Add Wallet
        </button>
      </div>

      {/* Wallets Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-lg shadow-sm border p-6 animate-pulse">
              <div className="h-6 bg-slate-200 rounded w-3/4 mb-4"></div>
              <div className="h-4 bg-slate-200 rounded w-1/2 mb-2"></div>
              <div className="h-4 bg-slate-200 rounded w-1/4"></div>
            </div>
          ))}
        </div>
      ) : wallets.length === 0 ? (
        <div className="bg-white rounded-lg shadow-sm border p-12 text-center">
          <Wallet className="w-16 h-16 mx-auto mb-4 text-slate-300" />
          <h3 className="text-lg font-medium text-slate-700 mb-2">No wallets yet</h3>
          <p className="text-slate-500 mb-4">Add your first wallet to start tracking your crypto</p>
          <button
            onClick={() => setShowAddModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition"
          >
            <Plus className="w-4 h-4" />
            Add Wallet
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {wallets.map((wallet) => {
            const chain = getChainInfo(wallet.chain);
            return (
              <div
                key={wallet.id}
                className="bg-white rounded-lg shadow-sm border p-6 hover:shadow-md transition"
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-10 h-10 ${chain.color} rounded-lg flex items-center justify-center`}
                    >
                      <Wallet className="w-5 h-5 text-white" />
                    </div>
                    <div>
                      <h3 className="font-medium text-slate-800">{chain.name}</h3>
                      <p className="text-xs text-slate-400 font-mono truncate max-w-[150px]" title={wallet.account_id}>
                        {wallet.account_id}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    {getStatusIcon(wallet.sync_status)}
                  </div>
                </div>

                {/* Pipeline progress bar */}
                {(wallet.sync_status === 'syncing' || wallet.sync_status === 'in_progress') && (
                  <div className="mb-4">
                    <SyncStatus walletId={wallet.id} compact={true} />
                  </div>
                )}

                <div className="flex items-center justify-between text-xs text-slate-400 mb-4">
                  <span>
                    {wallet.last_synced_at
                      ? `Synced ${new Date(wallet.last_synced_at).toLocaleDateString()}`
                      : 'Never synced'}
                  </span>
                </div>

                <div className="flex items-center gap-2 pt-4 border-t">
                  <button
                    onClick={() => handleSync(wallet.id)}
                    disabled={syncing === wallet.id}
                    className="flex-1 flex items-center justify-center gap-1 px-3 py-2 text-sm text-blue-600 hover:bg-blue-50 rounded-lg transition disabled:opacity-50"
                  >
                    <RefreshCw
                      className={`w-4 h-4 ${syncing === wallet.id ? 'animate-spin' : ''}`}
                    />
                    Sync
                  </button>
                  <button
                    onClick={() => handleDelete(wallet.id)}
                    disabled={deleting === wallet.id}
                    className="flex items-center justify-center px-3 py-2 text-sm text-red-600 hover:bg-red-50 rounded-lg transition disabled:opacity-50"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add Wallet Modal */}
      {showAddModal && (
        <AddWalletModal
          onClose={() => setShowAddModal(false)}
          onAdd={() => {
            setShowAddModal(false);
            fetchWallets();
          }}
        />
      )}
    </div>
  );
}

function AddWalletModal({ onClose, onAdd }: { onClose: () => void; onAdd: () => void }) {
  const [chain, setChain] = useState('NEAR');
  const [accountId, setAccountId] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await apiClient.post('/api/wallets', { account_id: accountId, chain });
      onAdd();
    } catch (err) {
      if (err instanceof ApiError) {
        const body = err.body as Record<string, unknown>;
        setError(String(body?.detail || 'Failed to add wallet'));
      } else {
        setError('Failed to add wallet');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Add Wallet</h2>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg">
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Blockchain</label>
            <select
              value={chain}
              onChange={(e) => setChain(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {CHAINS.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Wallet Address</label>
            <input
              type="text"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              placeholder={chain === 'NEAR' ? 'yourname.near' : '0x...'}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
              required
            />
          </div>

          {error && <p className="text-sm text-red-600 bg-red-50 p-3 rounded-lg">{error}</p>}

          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 border rounded-lg hover:bg-slate-50 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition disabled:opacity-50"
            >
              {loading ? 'Adding...' : 'Add Wallet'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

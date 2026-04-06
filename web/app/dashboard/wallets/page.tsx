'use client';

import { useState, useEffect, useMemo } from 'react';
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
  Search,
  ChevronDown,
  ChevronRight,
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
  { id: 'NEAR', name: 'NEAR Protocol', color: 'bg-green-500', textColor: 'text-green-700 dark:text-green-400', bgLight: 'bg-green-50 dark:bg-green-900/20' },
  { id: 'ETH', name: 'Ethereum', color: 'bg-blue-500', textColor: 'text-blue-700 dark:text-blue-400', bgLight: 'bg-blue-50 dark:bg-blue-900/20' },
  { id: 'Polygon', name: 'Polygon', color: 'bg-purple-500', textColor: 'text-purple-700 dark:text-purple-400', bgLight: 'bg-purple-50 dark:bg-purple-900/20' },
  { id: 'Cronos', name: 'Cronos', color: 'bg-blue-400', textColor: 'text-blue-700 dark:text-blue-300', bgLight: 'bg-blue-50 dark:bg-blue-900/20' },
  { id: 'Optimism', name: 'Optimism', color: 'bg-red-500', textColor: 'text-red-700 dark:text-red-400', bgLight: 'bg-red-50 dark:bg-red-900/20' },
];

export default function WalletsPage() {
  const [wallets, setWallets] = useState<WalletData[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [syncing, setSyncing] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [chainFilter, setChainFilter] = useState<string | null>(null);
  const [collapsedChains, setCollapsedChains] = useState<Set<string>>(new Set());

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

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'complete':
      case 'synced':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400">
            <CheckCircle className="w-3 h-3" />
            Synced
          </span>
        );
      case 'syncing':
      case 'in_progress':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
            <RefreshCw className="w-3 h-3 animate-spin" />
            Syncing
          </span>
        );
      case 'error':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400">
            <AlertCircle className="w-3 h-3" />
            Error
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-50 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400">
            <Clock className="w-3 h-3" />
            Pending
          </span>
        );
    }
  };

  const getChainInfo = (chainId: string) => {
    return CHAINS.find((c) => c.id === chainId) || {
      id: chainId, name: chainId, color: 'bg-gray-500',
      textColor: 'text-gray-700 dark:text-gray-400',
      bgLight: 'bg-gray-50 dark:bg-gray-900/20',
    };
  };

  // Filter and group wallets
  const filteredWallets = useMemo(() => {
    let filtered = wallets;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter((w) => w.account_id.toLowerCase().includes(q));
    }
    if (chainFilter) {
      filtered = filtered.filter((w) => w.chain === chainFilter);
    }
    return filtered;
  }, [wallets, searchQuery, chainFilter]);

  const groupedWallets = useMemo(() => {
    const groups: Record<string, WalletData[]> = {};
    for (const wallet of filteredWallets) {
      if (!groups[wallet.chain]) groups[wallet.chain] = [];
      groups[wallet.chain].push(wallet);
    }
    // Sort chains by the CHAINS order, then any unknown chains at end
    const chainOrder = CHAINS.map((c) => c.id);
    return Object.entries(groups).sort(([a], [b]) => {
      const ai = chainOrder.indexOf(a);
      const bi = chainOrder.indexOf(b);
      return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
    });
  }, [filteredWallets]);

  const toggleChainCollapse = (chainId: string) => {
    setCollapsedChains((prev) => {
      const next = new Set(prev);
      if (next.has(chainId)) next.delete(chainId);
      else next.add(chainId);
      return next;
    });
  };

  // Unique chains present in wallet data (for filter chips)
  const presentChains = useMemo(() => {
    const ids = new Set(wallets.map((w) => w.chain));
    return CHAINS.filter((c) => ids.has(c.id));
  }, [wallets]);

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
          <p className="text-slate-500">{wallets.length} wallet{wallets.length !== 1 ? 's' : ''} across {presentChains.length} chain{presentChains.length !== 1 ? 's' : ''}</p>
        </div>
        <button
          onClick={() => setShowAddModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition"
        >
          <Plus className="w-4 h-4" />
          Add Wallet
        </button>
      </div>

      {/* Search & Filters */}
      {wallets.length > 0 && (
        <div className="flex flex-col sm:flex-row gap-3">
          {/* Search */}
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by address..."
              className="w-full pl-9 pr-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-slate-100 dark:hover:bg-slate-700 rounded"
              >
                <X className="w-3.5 h-3.5 text-slate-400" />
              </button>
            )}
          </div>

          {/* Chain filter chips */}
          {presentChains.length > 1 && (
            <div className="flex items-center gap-2 flex-wrap">
              <button
                onClick={() => setChainFilter(null)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium transition ${
                  chainFilter === null
                    ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
                }`}
              >
                All
              </button>
              {presentChains.map((chain) => {
                const count = wallets.filter((w) => w.chain === chain.id).length;
                return (
                  <button
                    key={chain.id}
                    onClick={() => setChainFilter(chainFilter === chain.id ? null : chain.id)}
                    className={`px-3 py-1.5 rounded-full text-xs font-medium transition ${
                      chainFilter === chain.id
                        ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:hover:bg-slate-700'
                    }`}
                  >
                    {chain.name} ({count})
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700">
          <div className="p-6 space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-4 animate-pulse">
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-1/3"></div>
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-1/6"></div>
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-1/6"></div>
                <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-1/6"></div>
              </div>
            ))}
          </div>
        </div>
      ) : wallets.length === 0 ? (
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-12 text-center">
          <Wallet className="w-16 h-16 mx-auto mb-4 text-slate-300 dark:text-slate-600" />
          <h3 className="text-lg font-medium text-slate-700 dark:text-slate-300 mb-2">No wallets yet</h3>
          <p className="text-slate-500 mb-4">Add your first wallet to start tracking your crypto</p>
          <button
            onClick={() => setShowAddModal(true)}
            className="inline-flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition"
          >
            <Plus className="w-4 h-4" />
            Add Wallet
          </button>
        </div>
      ) : filteredWallets.length === 0 ? (
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-8 text-center">
          <Search className="w-10 h-10 mx-auto mb-3 text-slate-300 dark:text-slate-600" />
          <p className="text-slate-500">No wallets match your search</p>
          <button
            onClick={() => { setSearchQuery(''); setChainFilter(null); }}
            className="mt-2 text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400"
          >
            Clear filters
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {groupedWallets.map(([chainId, chainWallets]) => {
            const chain = getChainInfo(chainId);
            const isCollapsed = collapsedChains.has(chainId);
            const syncingCount = chainWallets.filter(
              (w) => w.sync_status === 'syncing' || w.sync_status === 'in_progress'
            ).length;

            return (
              <div
                key={chainId}
                className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden"
              >
                {/* Chain group header */}
                <button
                  onClick={() => toggleChainCollapse(chainId)}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition"
                >
                  {isCollapsed ? (
                    <ChevronRight className="w-4 h-4 text-slate-400" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-slate-400" />
                  )}
                  <div className={`w-2.5 h-2.5 rounded-full ${chain.color}`} />
                  <span className="font-medium text-slate-800 dark:text-slate-200">
                    {chain.name}
                  </span>
                  <span className="text-xs text-slate-400">
                    {chainWallets.length} wallet{chainWallets.length !== 1 ? 's' : ''}
                  </span>
                  {syncingCount > 0 && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400">
                      <RefreshCw className="w-3 h-3 animate-spin" />
                      {syncingCount} syncing
                    </span>
                  )}
                </button>

                {/* Table */}
                {!isCollapsed && (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead className="bg-slate-50 dark:bg-slate-900/50 border-y border-slate-200 dark:border-slate-700">
                        <tr>
                          <th className="px-4 py-2 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">
                            Address
                          </th>
                          <th className="px-4 py-2 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">
                            Status
                          </th>
                          <th className="px-4 py-2 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">
                            Last Synced
                          </th>
                          <th className="px-4 py-2 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">
                            Added
                          </th>
                          <th className="px-4 py-2 text-right text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">
                            Actions
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-700/50">
                        {chainWallets.map((wallet) => (
                          <tr
                            key={wallet.id}
                            className="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition"
                          >
                            <td className="px-4 py-3">
                              <span
                                className="text-sm font-mono text-slate-700 dark:text-slate-300"
                                title={wallet.account_id}
                              >
                                {wallet.account_id.length > 30
                                  ? `${wallet.account_id.slice(0, 8)}...${wallet.account_id.slice(-8)}`
                                  : wallet.account_id}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-2">
                                {getStatusBadge(wallet.sync_status)}
                                {(wallet.sync_status === 'syncing' || wallet.sync_status === 'in_progress') && (
                                  <SyncStatus walletId={wallet.id} compact={true} />
                                )}
                              </div>
                            </td>
                            <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">
                              {wallet.last_synced_at
                                ? new Date(wallet.last_synced_at).toLocaleDateString()
                                : <span className="text-slate-400 dark:text-slate-500">Never</span>}
                            </td>
                            <td className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">
                              {new Date(wallet.created_at).toLocaleDateString()}
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center justify-end gap-1">
                                <button
                                  onClick={() => handleSync(wallet.id)}
                                  disabled={syncing === wallet.id}
                                  className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 dark:hover:text-blue-400 dark:hover:bg-blue-900/30 rounded-md transition disabled:opacity-50"
                                  title="Sync wallet"
                                >
                                  <RefreshCw
                                    className={`w-4 h-4 ${syncing === wallet.id ? 'animate-spin' : ''}`}
                                  />
                                </button>
                                <button
                                  onClick={() => handleDelete(wallet.id)}
                                  disabled={deleting === wallet.id}
                                  className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:text-red-400 dark:hover:bg-red-900/30 rounded-md transition disabled:opacity-50"
                                  title="Delete wallet"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
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
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-md p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold text-slate-900 dark:text-white">Add Wallet</h2>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg">
            <X className="w-5 h-5 text-slate-400" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Blockchain</label>
            <select
              value={chain}
              onChange={(e) => setChain(e.target.value)}
              className="w-full px-3 py-2 border border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {CHAINS.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">Wallet Address</label>
            <input
              type="text"
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              placeholder={chain === 'NEAR' ? 'yourname.near' : '0x...'}
              className="w-full px-3 py-2 border border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
              required
            />
          </div>

          {error && <p className="text-sm text-red-600 bg-red-50 dark:bg-red-900/20 dark:text-red-400 p-3 rounded-lg">{error}</p>}

          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 border border-slate-200 dark:border-slate-600 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition"
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

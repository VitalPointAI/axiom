'use client';

import { useState, useEffect } from 'react';
import { 
  Wallet, 
  Plus, 
  RefreshCw, 
  Trash2, 
  Edit2,
  CheckCircle,
  Clock,
  AlertCircle,
  X
} from 'lucide-react';

interface WalletData {
  id: number;
  address: string;
  chain: string;
  label: string;
  sync_status: string;
  last_synced_at: string | null;
  created_at: string;
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

  const fetchWallets = async () => {
    try {
      const res = await fetch('/api/wallets');
      const data = await res.json();
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
      await fetch(`/api/wallets/${walletId}/sync`, { method: 'POST' });
      // Refresh wallets after sync
      await fetchWallets();
    } catch (error) {
      console.error('Sync failed:', error);
    } finally {
      setSyncing(null);
    }
  };

  const handleDelete = async (walletId: number) => {
    if (!confirm('Are you sure you want to delete this wallet? All associated transactions will be removed.')) {
      return;
    }
    
    try {
      await fetch(`/api/wallets/${walletId}`, { method: 'DELETE' });
      await fetchWallets();
    } catch (error) {
      console.error('Delete failed:', error);
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
    return CHAINS.find(c => c.id === chainId) || { id: chainId, name: chainId, color: 'bg-gray-500' };
  };

  return (
    <div className="space-y-6">
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
          {[1, 2, 3].map(i => (
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
          {wallets.map(wallet => {
            const chain = getChainInfo(wallet.chain);
            return (
              <div key={wallet.id} className="bg-white rounded-lg shadow-sm border p-6 hover:shadow-md transition">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 ${chain.color} rounded-lg flex items-center justify-center`}>
                      <Wallet className="w-5 h-5 text-white" />
                    </div>
                    <div>
                      <h3 className="font-medium text-slate-800">{wallet.label}</h3>
                      <p className="text-xs text-slate-400">{chain.name}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    {getStatusIcon(wallet.sync_status)}
                  </div>
                </div>

                <div className="mb-4">
                  <p className="text-sm font-mono text-slate-600 truncate" title={wallet.address}>
                    {wallet.address}
                  </p>
                </div>

                <div className="flex items-center justify-between text-xs text-slate-400">
                  <span>
                    {wallet.last_synced_at 
                      ? `Synced ${new Date(wallet.last_synced_at).toLocaleDateString()}`
                      : 'Never synced'
                    }
                  </span>
                </div>

                <div className="flex items-center gap-2 mt-4 pt-4 border-t">
                  <button
                    onClick={() => handleSync(wallet.id)}
                    disabled={syncing === wallet.id}
                    className="flex-1 flex items-center justify-center gap-1 px-3 py-2 text-sm text-blue-600 hover:bg-blue-50 rounded-lg transition disabled:opacity-50"
                  >
                    <RefreshCw className={`w-4 h-4 ${syncing === wallet.id ? 'animate-spin' : ''}`} />
                    Sync
                  </button>
                  <button
                    onClick={() => handleDelete(wallet.id)}
                    className="flex items-center justify-center px-3 py-2 text-sm text-red-600 hover:bg-red-50 rounded-lg transition"
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
  const [address, setAddress] = useState('');
  const [label, setLabel] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch('/api/wallets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chain, address, label }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.error || 'Failed to add wallet');
      }

      onAdd();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add wallet');
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
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Blockchain
            </label>
            <select
              value={chain}
              onChange={(e) => setChain(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {CHAINS.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Wallet Address
            </label>
            <input
              type="text"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              placeholder={chain === 'NEAR' ? 'yourname.near' : '0x...'}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              Label (optional)
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="My main wallet"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {error && (
            <p className="text-sm text-red-600 bg-red-50 p-3 rounded-lg">{error}</p>
          )}

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

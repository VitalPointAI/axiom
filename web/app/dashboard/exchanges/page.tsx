'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { 
  Plus, 
  Trash2, 
  RefreshCw, 
  CheckCircle, 
  XCircle, 
  Loader2,
  FileSpreadsheet,
  Key,
  X
} from 'lucide-react';

interface ImportBatch {
  id: number;
  filename: string;
  exchange: string;
  row_count: number;
  imported_count: number;
  skipped_count: number;
  error_count: number;
  status: string;
  created_at: string;
}

interface ExchangeConnection {
  id: number;
  exchange: string;
  label: string;
  status: string;
  last_sync: string | null;
  created_at: string;
}

const exchangeInfo: Record<string, { name: string; logo: string; supportsApi?: boolean }> = {
  'crypto.com': { name: 'Crypto.com App', logo: '🔷' },
  'coinbase': { name: 'Coinbase', logo: '🔵' },
  'coinbase_pro': { name: 'Coinbase Advanced Trade', logo: '🔵', supportsApi: true },
  'coinsquare': { name: 'Coinsquare', logo: '🟡' },
  'newton': { name: 'Newton', logo: '🍎' },
  'shakepay': { name: 'Shakepay', logo: '🟢' },
  'kraken': { name: 'Kraken', logo: '🐙' },
  'binance': { name: 'Binance', logo: '🟨' },
  'generic': { name: 'Other', logo: '📄' },
};

export default function ExchangesPage() {
  const router = useRouter();
  const [batches, setBatches] = useState<ImportBatch[]>([]);
  const [connections, setConnections] = useState<ExchangeConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [showConnectModal, setShowConnectModal] = useState(false);
  const [selectedExchange, setSelectedExchange] = useState<string | null>(null);
  const [apiCredentials, setApiCredentials] = useState({ 
    key_id: '', 
    api_key_name: '', 
    private_key: '', 
    label: '' 
  });
  const [connecting, setConnecting] = useState(false);
  const [syncing, setSyncing] = useState<number | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const batchesRes = await fetch('/api/import/csv');
      const batchesData = await batchesRes.json();
      setBatches(batchesData.batches || []);

      const connectionsRes = await fetch('/api/exchanges/connections');
      if (connectionsRes.ok) {
        const connectionsData = await connectionsRes.json();
        setConnections(connectionsData.connections || []);
      }
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleDeleteBatch = async (batchId: number) => {
    if (!confirm('Delete this import and all its transactions?')) return;

    try {
      const res = await fetch(`/api/import/csv?id=${batchId}`, { method: 'DELETE' });
      if (res.ok) {
        setMessage({ type: 'success', text: 'Import deleted' });
        fetchData();
      }
    } catch {
      setMessage({ type: 'error', text: 'Failed to delete import' });
    }
  };

  const handleConnectExchange = (exchangeId: string) => {
    setSelectedExchange(exchangeId);
    setApiCredentials({ 
      key_id: '', 
      api_key_name: '', 
      private_key: '', 
      label: exchangeInfo[exchangeId]?.name || exchangeId 
    });
    setShowConnectModal(true);
  };

  const handleSaveConnection = async () => {
    if (!selectedExchange || !apiCredentials.key_id || !apiCredentials.private_key) {
      setMessage({ type: 'error', text: 'Key ID and Private Key are required' });
      return;
    }

    setConnecting(true);
    try {
      const res = await fetch('/api/exchanges/connections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          exchange: selectedExchange,
          label: apiCredentials.label,
          api_key: apiCredentials.key_id,
          api_secret: apiCredentials.private_key,
          api_key_name: apiCredentials.api_key_name,
        }),
      });

      if (res.ok) {
        setMessage({ type: 'success', text: 'Exchange connected!' });
        setShowConnectModal(false);
        fetchData();
      } else {
        const data = await res.json();
        setMessage({ type: 'error', text: data.error || 'Failed to connect' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Failed to connect exchange' });
    } finally {
      setConnecting(false);
    }
  };

  const handleSyncConnection = async (connectionId: number) => {
    setSyncing(connectionId);
    try {
      const res = await fetch(`/api/exchanges/connections/${connectionId}/sync`, { method: 'POST' });
      if (res.ok) {
        setMessage({ type: 'success', text: 'Sync started' });
        fetchData();
      } else {
        setMessage({ type: 'error', text: 'Sync failed' });
      }
    } catch {
      setMessage({ type: 'error', text: 'Sync failed' });
    } finally {
      setSyncing(null);
    }
  };

  const handleDeleteConnection = async (connectionId: number) => {
    if (!confirm('Disconnect this exchange?')) return;

    try {
      const res = await fetch(`/api/exchanges/connections?id=${connectionId}`, { method: 'DELETE' });
      if (res.ok) {
        setMessage({ type: 'success', text: 'Exchange disconnected' });
        fetchData();
      }
    } catch {
      setMessage({ type: 'error', text: 'Failed to disconnect' });
    }
  };

  const getExchangeDisplay = (exchangeId: string) => {
    return exchangeInfo[exchangeId] || { name: exchangeId, logo: '📊' };
  };

  const batchesByExchange = batches.reduce((acc, batch) => {
    const key = batch.exchange || 'unknown';
    if (!acc[key]) acc[key] = [];
    acc[key].push(batch);
    return acc;
  }, {} as Record<string, ImportBatch[]>);

  if (loading) {
    return (
      <div className="p-8 text-center">
        <Loader2 className="w-8 h-8 animate-spin mx-auto text-blue-500" />
        <p className="mt-2 text-slate-500">Loading exchanges...</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto py-8 px-4 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Exchanges</h1>
          <p className="text-slate-500 mt-1">Manage your exchange imports and API connections</p>
        </div>
        <button
          onClick={() => router.push('/dashboard/import')}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
        >
          <Plus className="w-4 h-4" />
          Import CSV
        </button>
      </div>

      {/* Message */}
      {message && (
        <div className={`p-4 rounded-lg flex items-center gap-2 ${
          message.type === 'success' 
            ? 'bg-green-50 text-green-800 border border-green-200'
            : 'bg-red-50 text-red-800 border border-red-200'
        }`}>
          {message.type === 'success' ? <CheckCircle className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
          {message.text}
          <button onClick={() => setMessage(null)} className="ml-auto">×</button>
        </div>
      )}

      {/* API Connections */}
      {connections.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-white flex items-center gap-2">
            <Key className="w-5 h-5" />
            API Connections
          </h2>
          <div className="grid gap-3">
            {connections.map((conn) => {
              const info = getExchangeDisplay(conn.exchange);
              return (
                <div key={conn.id} className="bg-white dark:bg-slate-800 rounded-xl border p-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">{info.logo}</span>
                    <div>
                      <h3 className="font-semibold text-slate-900 dark:text-white">{conn.label || info.name}</h3>
                      <p className="text-sm text-slate-500">
                        {conn.status === 'active' ? '✅ Connected' : '⚠️ ' + conn.status}
                        {conn.last_sync && ` • Last sync: ${new Date(conn.last_sync).toLocaleString()}`}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleSyncConnection(conn.id)}
                      disabled={syncing === conn.id}
                      className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition disabled:opacity-50"
                      title="Sync now"
                    >
                      <RefreshCw className={`w-5 h-5 ${syncing === conn.id ? 'animate-spin' : ''}`} />
                    </button>
                    <button
                      onClick={() => handleDeleteConnection(conn.id)}
                      className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition"
                      title="Disconnect"
                    >
                      <Trash2 className="w-5 h-5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* CSV Imports */}
      {Object.keys(batchesByExchange).length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold text-slate-800 dark:text-white flex items-center gap-2">
            <FileSpreadsheet className="w-5 h-5" />
            CSV Imports
          </h2>
          <div className="grid gap-4">
            {Object.entries(batchesByExchange).map(([exchangeId, exchangeBatches]) => {
              const info = getExchangeDisplay(exchangeId);
              const totalImported = exchangeBatches.reduce((sum, b) => sum + (b.imported_count || 0), 0);

              return (
                <div key={exchangeId} className="bg-white dark:bg-slate-800 rounded-xl border overflow-hidden">
                  <div className="p-4 flex items-center justify-between border-b bg-slate-50 dark:bg-slate-700">
                    <div className="flex items-center gap-3">
                      <span className="text-2xl">{info.logo}</span>
                      <div>
                        <h3 className="font-semibold text-slate-900 dark:text-white">{info.name}</h3>
                        <p className="text-sm text-slate-500">
                          {totalImported.toLocaleString()} transactions • {exchangeBatches.length} imports
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => router.push(`/dashboard/import?exchange=${exchangeId}`)}
                      className="px-3 py-1.5 text-sm bg-blue-100 text-blue-700 rounded-lg hover:bg-blue-200 transition"
                    >
                      Import More
                    </button>
                  </div>
                  <div className="divide-y dark:divide-slate-700">
                    {exchangeBatches.slice(0, 3).map((batch) => (
                      <div key={batch.id} className="p-3 flex items-center justify-between hover:bg-slate-50 dark:hover:bg-slate-700">
                        <div className="flex items-center gap-3">
                          <FileSpreadsheet className="w-4 h-4 text-slate-400" />
                          <div>
                            <p className="text-sm font-medium text-slate-700 dark:text-slate-200">{batch.filename}</p>
                            <p className="text-xs text-slate-500">
                              {batch.imported_count} imported • {new Date(batch.created_at).toLocaleDateString()}
                            </p>
                          </div>
                        </div>
                        <button
                          onClick={() => handleDeleteBatch(batch.id)}
                          className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded transition"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Empty State */}
      {Object.keys(batchesByExchange).length === 0 && connections.length === 0 && (
        <div className="bg-white dark:bg-slate-800 rounded-xl border p-12 text-center">
          <div className="w-16 h-16 bg-slate-100 dark:bg-slate-700 rounded-full flex items-center justify-center mx-auto mb-4">
            <FileSpreadsheet className="w-8 h-8 text-slate-400" />
          </div>
          <h3 className="font-semibold text-slate-900 dark:text-white">No exchanges connected yet</h3>
          <p className="text-slate-500 mt-1 mb-4">Connect via API or import CSV files</p>
        </div>
      )}

      {/* Connect Exchange Options */}
      <div className="bg-slate-50 dark:bg-slate-800 rounded-xl p-4">
        <h3 className="font-medium text-slate-700 dark:text-slate-200 text-sm mb-3">Connect an Exchange</h3>
        
        <div className="mb-4">
          <p className="text-xs text-slate-500 mb-2">🔗 Connect via API (automatic sync)</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(exchangeInfo).filter(([_, info]) => info.supportsApi).map(([id, info]) => (
              <button
                key={id}
                onClick={() => handleConnectExchange(id)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-slate-700 border-2 border-blue-200 rounded-lg text-sm hover:bg-blue-50 hover:border-blue-400 transition"
              >
                <span>{info.logo}</span>
                <span className="text-slate-700 dark:text-slate-200">{info.name}</span>
                <Key className="w-3 h-3 text-blue-500" />
              </button>
            ))}
          </div>
        </div>

        <div>
          <p className="text-xs text-slate-500 mb-2">📄 Import from CSV</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(exchangeInfo).filter(([id]) => id !== 'generic').map(([id, info]) => (
              <button
                key={id}
                onClick={() => router.push(`/dashboard/import?exchange=${id}`)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white dark:bg-slate-700 border rounded-lg text-sm hover:bg-blue-50 hover:border-blue-200 transition"
              >
                <span>{info.logo}</span>
                <span className="text-slate-700 dark:text-slate-200">{info.name}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Connect Modal - Coinbase Advanced Trade */}
      {showConnectModal && selectedExchange === 'coinbase_pro' && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-slate-800 rounded-2xl max-w-md w-full p-6 shadow-xl">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-3">
                <span className="text-3xl">🔵</span>
                <div>
                  <h2 className="text-xl font-bold text-slate-900 dark:text-white">Connect Coinbase Advanced</h2>
                  <p className="text-sm text-slate-500">Enter your API credentials</p>
                </div>
              </div>
              <button onClick={() => setShowConnectModal(false)} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-200 mb-1">Label (optional)</label>
                <input
                  type="text"
                  value={apiCredentials.label}
                  onChange={(e) => setApiCredentials({ ...apiCredentials, label: e.target.value })}
                  placeholder="My Coinbase Account"
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-slate-700 dark:border-slate-600"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-200 mb-1">Key ID *</label>
                <input
                  type="text"
                  value={apiCredentials.key_id}
                  onChange={(e) => setApiCredentials({ ...apiCredentials, key_id: e.target.value })}
                  placeholder="e.g., abc123def..."
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 font-mono text-sm dark:bg-slate-700 dark:border-slate-600"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-200 mb-1">API Key Name</label>
                <input
                  type="text"
                  value={apiCredentials.api_key_name}
                  onChange={(e) => setApiCredentials({ ...apiCredentials, api_key_name: e.target.value })}
                  placeholder="e.g., NearTax Sync"
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 text-sm dark:bg-slate-700 dark:border-slate-600"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 dark:text-slate-200 mb-1">Private Key *</label>
                <textarea
                  value={apiCredentials.private_key}
                  onChange={(e) => setApiCredentials({ ...apiCredentials, private_key: e.target.value })}
                  placeholder="-----BEGIN EC PRIVATE KEY-----&#10;...&#10;-----END EC PRIVATE KEY-----"
                  rows={5}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 font-mono text-xs dark:bg-slate-700 dark:border-slate-600"
                />
              </div>

              <div className="bg-blue-50 dark:bg-blue-900/30 rounded-lg p-3 text-sm">
                <p className="font-medium text-blue-800 dark:text-blue-200 mb-1">Where to get API keys:</p>
                <p className="text-blue-700 dark:text-blue-300">
                  Go to <a href="https://www.coinbase.com/settings/api" target="_blank" rel="noopener" className="underline">Coinbase Settings → API</a> → Create New API Key
                </p>
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowConnectModal(false)}
                className="flex-1 px-4 py-2 border rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 transition"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveConnection}
                disabled={connecting || !apiCredentials.key_id || !apiCredentials.private_key}
                className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {connecting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Key className="w-4 h-4" />}
                {connecting ? 'Connecting...' : 'Connect'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

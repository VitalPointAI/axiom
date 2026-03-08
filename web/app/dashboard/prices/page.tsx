'use client';

import { useState, useEffect } from 'react';
import { AlertTriangle, CheckCircle, Trash2, RefreshCw, DollarSign } from 'lucide-react';

interface PriceWarning {
  id: number;
  tx_hash: string;
  wallet_address: string;
  amount_near: number;
  datetime: string;
  price_warning: string;
  price_warning_msg: string;
  price_resolved: number;
  price_manual_usd: number;
  action_type: string;
  method_name: string;
}

interface Summary {
  price_warning: string;
  count: number;
  resolved_count: number;
}

export default function PricesPage() {
  const [summary, setSummary] = useState<Summary[]>([]);
  const [transactions, setTransactions] = useState<PriceWarning[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedType, setSelectedType] = useState<string>('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [resolving, setResolving] = useState<number | null>(null);
  const [bulkResolving, setBulkResolving] = useState(false);

  useEffect(() => {
    fetchWarnings();
  }, [selectedType, page]);

  const fetchWarnings = async () => {
    try {
      const params = new URLSearchParams();
      if (selectedType) params.set('type', selectedType);
      params.set('page', page.toString());
      params.set('limit', '50');
      
      const res = await fetch(`/api/price-warnings?${params}`);
      const data = await res.json();
      setSummary(data.summary);
      setTransactions(data.transactions);
      setTotal(data.total);
    } catch (err) {
      console.error('Failed to fetch price warnings:', err);
    } finally {
      setLoading(false);
    }
  };

  const resolveAsSpam = async (txId: number) => {
    setResolving(txId);
    try {
      await fetch('/api/price-warnings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ txId, action: 'mark_spam' })
      });
      fetchWarnings();
    } finally {
      setResolving(null);
    }
  };

  const bulkResolveSpam = async () => {
    setBulkResolving(true);
    try {
      const res = await fetch('/api/price-warnings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'bulk_resolve_spam' })
      });
      const data = await res.json();
      alert(`Resolved ${data.resolved} spam transactions`);
      fetchWarnings();
    } finally {
      setBulkResolving(false);
    }
  };

  const getWarningLabel = (type: string) => {
    switch (type) {
      case 'spam_token': return 'Spam Token';
      case 'no_price_data': return 'No Price Data';
      case 'manual_required': return 'Manual Review';
      default: return type;
    }
  };

  const getWarningColor = (type: string) => {
    switch (type) {
      case 'spam_token': return 'bg-slate-100 text-slate-700';
      case 'no_price_data': return 'bg-orange-100 text-orange-700';
      case 'manual_required': return 'bg-red-100 text-red-700';
      default: return 'bg-slate-100 text-slate-700';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-8 h-8 animate-spin text-slate-400" />
      </div>
    );
  }

  const unresolvedSpam = summary.find(s => s.price_warning === 'spam_token');
  const spamCount = unresolvedSpam ? unresolvedSpam.count - unresolvedSpam.resolved_count : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Price Warnings</h1>
          <p className="text-slate-500">
            Review and resolve transactions with missing or uncertain prices
          </p>
        </div>
        {spamCount > 0 && (
          <button
            onClick={bulkResolveSpam}
            disabled={bulkResolving}
            className="flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800 transition disabled:opacity-50"
          >
            {bulkResolving ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Trash2 className="w-4 h-4" />
            )}
            Resolve All Spam ({spamCount})
          </button>
        )}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {summary.map(s => (
          <div
            key={s.price_warning}
            onClick={() => setSelectedType(selectedType === s.price_warning ? '' : s.price_warning)}
            className={`cursor-pointer rounded-lg shadow-sm border p-6 transition ${
              selectedType === s.price_warning ? 'ring-2 ring-blue-500' : ''
            } ${getWarningColor(s.price_warning).replace('text-', 'border-').split(' ')[0]}`}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-slate-500">{getWarningLabel(s.price_warning)}</p>
                <p className="text-2xl font-bold text-slate-900">{s.count - s.resolved_count}</p>
                <p className="text-xs text-slate-400">{s.resolved_count} resolved</p>
              </div>
              <AlertTriangle className={`w-8 h-8 ${
                s.price_warning === 'spam_token' ? 'text-slate-400' :
                s.price_warning === 'no_price_data' ? 'text-orange-400' :
                'text-red-400'
              }`} />
            </div>
          </div>
        ))}
      </div>

      {/* Transactions Table */}
      <div className="bg-white rounded-lg shadow-sm border">
        <div className="p-4 border-b">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-slate-700">
              {selectedType ? getWarningLabel(selectedType) : 'All'} Transactions
            </h2>
            <span className="text-sm text-slate-500">{total} total</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-slate-50">
              <tr>
                <th className="text-left px-4 py-3 text-slate-500 font-medium">Date</th>
                <th className="text-left px-4 py-3 text-slate-500 font-medium">Wallet</th>
                <th className="text-left px-4 py-3 text-slate-500 font-medium">Type</th>
                <th className="text-right px-4 py-3 text-slate-500 font-medium">Amount</th>
                <th className="text-left px-4 py-3 text-slate-500 font-medium">Warning</th>
                <th className="text-right px-4 py-3 text-slate-500 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map(tx => (
                <tr key={tx.id} className="border-b last:border-0 hover:bg-slate-50">
                  <td className="px-4 py-3 text-sm">
                    {tx.datetime ? new Date(tx.datetime + 'Z').toLocaleDateString() : 'Unknown'}
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-sm">
                      {tx.wallet_address?.slice(0, 12)}...
                    </span>
                  </td>
                  <td className="px-4 py-3 text-sm">
                    {tx.method_name || tx.action_type || 'Transfer'}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <span className="font-mono">
                      {tx.amount_near?.toFixed(4)} NEAR
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded text-xs ${getWarningColor(tx.price_warning)}`}>
                      {getWarningLabel(tx.price_warning)}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {tx.price_warning === 'spam_token' && !tx.price_resolved && (
                        <button
                          onClick={() => resolveAsSpam(tx.id)}
                          disabled={resolving === tx.id}
                          className="p-2 text-slate-400 hover:text-red-500 transition"
                          title="Mark as spam ($0)"
                        >
                          {resolving === tx.id ? (
                            <RefreshCw className="w-4 h-4 animate-spin" />
                          ) : (
                            <Trash2 className="w-4 h-4" />
                          )}
                        </button>
                      )}
                      {tx.price_resolved ? (
                        <CheckCircle className="w-5 h-5 text-green-500" />
                      ) : (
                        <button
                          className="p-2 text-slate-400 hover:text-blue-500 transition"
                          title="Set manual price"
                        >
                          <DollarSign className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {total > 50 && (
          <div className="p-4 border-t flex items-center justify-between">
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              className="px-4 py-2 border rounded-lg disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-sm text-slate-500">
              Page {page} of {Math.ceil(total / 50)}
            </span>
            <button
              onClick={() => setPage(p => p + 1)}
              disabled={page >= Math.ceil(total / 50)}
              className="px-4 py-2 border rounded-lg disabled:opacity-50"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

'use client';

import { useState, useEffect } from 'react';
import { 
  ArrowLeftRight, 
  ArrowUpRight, 
  ArrowDownRight,
  Filter,
  Search,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink
} from 'lucide-react';

interface Transaction {
  id: number;
  wallet_id: number;
  tx_hash: string;
  timestamp: string;
  tx_type: string;
  from_address: string;
  to_address: string;
  asset: string;
  amount: number;
  fee: number;
  fee_asset: string;
  classification: string;
  notes: string;
  chain: string;
  wallet_label: string;
}

interface Pagination {
  page: number;
  limit: number;
  total: number;
  totalPages: number;
}

interface Filters {
  types: string[];
  assets: string[];
}

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [pagination, setPagination] = useState<Pagination>({ page: 1, limit: 25, total: 0, totalPages: 0 });
  const [filters, setFilters] = useState<Filters>({ types: [], assets: [] });
  const [loading, setLoading] = useState(true);

  // Filter state
  const [selectedType, setSelectedType] = useState('');
  const [selectedAsset, setSelectedAsset] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [showFilters, setShowFilters] = useState(false);

  const fetchTransactions = async (page = 1) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: '25',
      });
      
      if (selectedType) params.set('type', selectedType);
      if (selectedAsset) params.set('asset', selectedAsset);
      if (searchQuery) params.set('q', searchQuery);

      const res = await fetch(`/api/transactions?${params}`);
      const data = await res.json();
      
      setTransactions(data.transactions || []);
      setPagination(data.pagination || { page: 1, limit: 25, total: 0, totalPages: 0 });
      setFilters(data.filters || { types: [], assets: [] });
    } catch (error) {
      console.error('Failed to fetch transactions:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTransactions();
  }, [selectedType, selectedAsset]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchTransactions(1);
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'transfer':
        return <ArrowLeftRight className="w-4 h-4" />;
      case 'stake':
      case 'unstake':
        return <ArrowUpRight className="w-4 h-4" />;
      default:
        return <ArrowDownRight className="w-4 h-4" />;
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'transfer':
        return 'text-blue-600 bg-blue-50';
      case 'stake':
        return 'text-green-600 bg-green-50';
      case 'unstake':
        return 'text-orange-600 bg-orange-50';
      case 'swap':
        return 'text-purple-600 bg-purple-50';
      default:
        return 'text-slate-600 bg-slate-50';
    }
  };

  const formatAddress = (addr: string) => {
    if (!addr) return '-';
    if (addr.length <= 20) return addr;
    return `${addr.slice(0, 8)}...${addr.slice(-6)}`;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Transactions</h1>
          <p className="text-slate-500">{pagination.total} total transactions</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 border rounded-lg hover:bg-slate-50 transition">
          <Download className="w-4 h-4" />
          Export CSV
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow-sm border p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Search */}
          <form onSubmit={handleSearch} className="flex-1 min-w-[200px]">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by hash, address, or notes..."
                className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
          </form>

          {/* Type filter */}
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            className="px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Types</option>
            {filters.types.map(type => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>

          {/* Asset filter */}
          <select
            value={selectedAsset}
            onChange={(e) => setSelectedAsset(e.target.value)}
            className="px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Assets</option>
            {filters.assets.map(asset => (
              <option key={asset} value={asset}>{asset}</option>
            ))}
          </select>

          {(selectedType || selectedAsset || searchQuery) && (
            <button
              onClick={() => {
                setSelectedType('');
                setSelectedAsset('');
                setSearchQuery('');
                fetchTransactions(1);
              }}
              className="text-sm text-blue-500 hover:underline"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* Transactions Table */}
      <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
        {loading ? (
          <div className="p-8 text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-400 mx-auto"></div>
          </div>
        ) : transactions.length === 0 ? (
          <div className="p-12 text-center text-slate-500">
            <ArrowLeftRight className="w-12 h-12 mx-auto mb-4 text-slate-300" />
            <p>No transactions found</p>
            <p className="text-sm">Sync a wallet to see transactions</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 border-b">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Date</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Type</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Asset</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-slate-500 uppercase">Amount</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">From/To</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Wallet</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">Hash</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {transactions.map((tx) => (
                  <tr key={tx.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 text-sm text-slate-600">
                      {new Date(tx.timestamp).toLocaleDateString()}
                      <br />
                      <span className="text-xs text-slate-400">
                        {new Date(tx.timestamp).toLocaleTimeString()}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${getTypeColor(tx.tx_type)}`}>
                        {getTypeIcon(tx.tx_type)}
                        {tx.tx_type || 'unknown'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm font-medium text-slate-800">
                      {tx.asset}
                    </td>
                    <td className="px-4 py-3 text-sm text-right font-mono">
                      {tx.amount?.toLocaleString(undefined, { maximumFractionDigits: 6 })}
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-600 font-mono">
                      <div title={tx.from_address}>{formatAddress(tx.from_address)}</div>
                      <div className="text-xs text-slate-400">→ {formatAddress(tx.to_address)}</div>
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-600">
                      {tx.wallet_label}
                      <br />
                      <span className="text-xs text-slate-400">{tx.chain}</span>
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <a
                        href={`https://nearblocks.io/txns/${tx.tx_hash}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-blue-500 hover:underline font-mono"
                      >
                        {tx.tx_hash.slice(0, 8)}...
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {pagination.totalPages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t">
            <p className="text-sm text-slate-500">
              Showing {(pagination.page - 1) * pagination.limit + 1} to{' '}
              {Math.min(pagination.page * pagination.limit, pagination.total)} of {pagination.total}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => fetchTransactions(pagination.page - 1)}
                disabled={pagination.page <= 1}
                className="p-2 border rounded-lg hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-sm text-slate-600">
                Page {pagination.page} of {pagination.totalPages}
              </span>
              <button
                onClick={() => fetchTransactions(pagination.page + 1)}
                disabled={pagination.page >= pagination.totalPages}
                className="p-2 border rounded-lg hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

'use client';

import { useState, useEffect, useCallback } from 'react';
import { 
  ArrowLeftRight, 
  ArrowUpRight, 
  ArrowDownRight,
  Search,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Download,
  ExternalLink,
  Coins,
  Landmark,
  RefreshCw,
  FileText,
  Palette,
  Zap,
  ArrowUp,
  ArrowDown,
  Filter,
  X
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
  tax_category: string;
  needs_review: boolean;
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
  categories: string[];
}

type SortField = 'timestamp' | 'tx_type' | 'asset' | 'amount' | 'tax_category' | 'wallet_label';
type SortDir = 'asc' | 'desc';

const TAX_CATEGORY_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  'transfer': { label: 'Transfer', color: 'text-blue-600 bg-blue-50', icon: <ArrowLeftRight className="w-3 h-3" /> },
  'staking': { label: 'Staking', color: 'text-green-600 bg-green-50', icon: <Landmark className="w-3 h-3" /> },
  'unstaking': { label: 'Unstaking', color: 'text-yellow-600 bg-yellow-50', icon: <ArrowUpRight className="w-3 h-3" /> },
  'swap': { label: 'Swap', color: 'text-purple-600 bg-purple-50', icon: <RefreshCw className="w-3 h-3" /> },
  'defi-lending': { label: 'DeFi Lending', color: 'text-cyan-600 bg-cyan-50', icon: <Coins className="w-3 h-3" /> },
  'liquid-staking': { label: 'Liquid Staking', color: 'text-teal-600 bg-teal-50', icon: <Zap className="w-3 h-3" /> },
  'nft': { label: 'NFT', color: 'text-pink-600 bg-pink-50', icon: <Palette className="w-3 h-3" /> },
  'contract-call': { label: 'Contract Call', color: 'text-slate-600 bg-slate-100', icon: <FileText className="w-3 h-3" /> },
  'uncategorized': { label: 'Uncategorized', color: 'text-gray-500 bg-gray-50', icon: <ArrowDownRight className="w-3 h-3" /> },
};

const PAGE_SIZES = [10, 25, 50, 100];

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [pagination, setPagination] = useState<Pagination>({ page: 1, limit: 25, total: 0, totalPages: 0 });
  const [filters, setFilters] = useState<Filters>({ types: [], assets: [], categories: [] });
  const [loading, setLoading] = useState(true);

  // Filter state
  const [selectedType, setSelectedType] = useState('');
  const [selectedAsset, setSelectedAsset] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [pageSize, setPageSize] = useState(25);
  const [goToPage, setGoToPage] = useState('');
  
  // Sort state
  const [sortField, setSortField] = useState<SortField>('timestamp');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  
  // Column filters
  const [showColumnFilters, setShowColumnFilters] = useState(false);
  const [columnFilters, setColumnFilters] = useState({
    wallet: '',
    address: '',
    minAmount: '',
    maxAmount: '',
  });

  const fetchTransactions = useCallback(async (page = 1) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: pageSize.toString(),
        sort: sortField,
        order: sortDir,
      });
      
      if (selectedType) params.set('type', selectedType);
      if (selectedAsset) params.set('asset', selectedAsset);
      if (selectedCategory) params.set('category', selectedCategory);
      if (searchQuery) params.set('q', searchQuery);
      if (columnFilters.wallet) params.set('wallet', columnFilters.wallet);
      if (columnFilters.address) params.set('address', columnFilters.address);
      if (columnFilters.minAmount) params.set('minAmount', columnFilters.minAmount);
      if (columnFilters.maxAmount) params.set('maxAmount', columnFilters.maxAmount);

      const res = await fetch(`/api/transactions?${params}`);
      const data = await res.json();
      
      setTransactions(data.transactions || []);
      setPagination(data.pagination || { page: 1, limit: pageSize, total: 0, totalPages: 0 });
      setFilters(data.filters || { types: [], assets: [], categories: [] });
    } catch (error) {
      console.error('Failed to fetch transactions:', error);
    } finally {
      setLoading(false);
    }
  }, [pageSize, sortField, sortDir, selectedType, selectedAsset, selectedCategory, searchQuery, columnFilters]);

  useEffect(() => {
    fetchTransactions(1);
  }, [pageSize, sortField, sortDir, selectedType, selectedAsset, selectedCategory]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchTransactions(1);
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const handleGoToPage = (e: React.FormEvent) => {
    e.preventDefault();
    const page = parseInt(goToPage);
    if (page >= 1 && page <= pagination.totalPages) {
      fetchTransactions(page);
      setGoToPage('');
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUp className="w-3 h-3 opacity-30" />;
    return sortDir === 'asc' 
      ? <ArrowUp className="w-3 h-3 text-blue-500" />
      : <ArrowDown className="w-3 h-3 text-blue-500" />;
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'transfer': return <ArrowLeftRight className="w-4 h-4" />;
      case 'stake':
      case 'unstake': return <ArrowUpRight className="w-4 h-4" />;
      default: return <ArrowDownRight className="w-4 h-4" />;
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'transfer': return 'text-blue-600 bg-blue-50';
      case 'stake': return 'text-green-600 bg-green-50';
      case 'unstake': return 'text-orange-600 bg-orange-50';
      case 'swap': return 'text-purple-600 bg-purple-50';
      default: return 'text-slate-600 bg-slate-50';
    }
  };

  const getTaxCategoryDisplay = (category: string) => {
    const config = TAX_CATEGORY_CONFIG[category] || TAX_CATEGORY_CONFIG['uncategorized'];
    return (
      <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.color}`}>
        {config.icon}
        {config.label}
      </span>
    );
  };

  const formatAddress = (addr: string) => {
    if (!addr) return '-';
    if (addr.length <= 20) return addr;
    return `${addr.slice(0, 8)}...${addr.slice(-6)}`;
  };

  const clearAllFilters = () => {
    setSelectedType('');
    setSelectedAsset('');
    setSelectedCategory('');
    setSearchQuery('');
    setColumnFilters({ wallet: '', address: '', minAmount: '', maxAmount: '' });
    fetchTransactions(1);
  };

  const hasActiveFilters = selectedType || selectedAsset || selectedCategory || searchQuery || 
    columnFilters.wallet || columnFilters.address || columnFilters.minAmount || columnFilters.maxAmount;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Transactions</h1>
          <p className="text-slate-500">{pagination.total.toLocaleString()} total transactions</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 border rounded-lg hover:bg-slate-50 transition">
          <Download className="w-4 h-4" />
          Export CSV
        </button>
      </div>

      {/* Filters Bar */}
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
                placeholder="Search by hash, address..."
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

          {/* Category filter */}
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Categories</option>
            {Object.entries(TAX_CATEGORY_CONFIG).map(([key, config]) => (
              <option key={key} value={key}>{config.label}</option>
            ))}
          </select>

          {/* Column Filters Toggle */}
          <button
            onClick={() => setShowColumnFilters(!showColumnFilters)}
            className={`flex items-center gap-2 px-3 py-2 border rounded-lg transition ${showColumnFilters ? 'bg-blue-50 border-blue-200' : 'hover:bg-slate-50'}`}
          >
            <Filter className="w-4 h-4" />
            Filters
          </button>

          {hasActiveFilters && (
            <button
              onClick={clearAllFilters}
              className="flex items-center gap-1 text-sm text-red-500 hover:text-red-700"
            >
              <X className="w-4 h-4" />
              Clear all
            </button>
          )}
        </div>

        {/* Column Filters */}
        {showColumnFilters && (
          <div className="mt-4 pt-4 border-t grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">Wallet</label>
              <input
                type="text"
                value={columnFilters.wallet}
                onChange={(e) => setColumnFilters(prev => ({ ...prev, wallet: e.target.value }))}
                placeholder="Filter by wallet..."
                className="w-full px-3 py-1.5 text-sm border rounded focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">Address</label>
              <input
                type="text"
                value={columnFilters.address}
                onChange={(e) => setColumnFilters(prev => ({ ...prev, address: e.target.value }))}
                placeholder="From/To address..."
                className="w-full px-3 py-1.5 text-sm border rounded focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">Min Amount</label>
              <input
                type="number"
                value={columnFilters.minAmount}
                onChange={(e) => setColumnFilters(prev => ({ ...prev, minAmount: e.target.value }))}
                placeholder="0"
                className="w-full px-3 py-1.5 text-sm border rounded focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 mb-1">Max Amount</label>
              <input
                type="number"
                value={columnFilters.maxAmount}
                onChange={(e) => setColumnFilters(prev => ({ ...prev, maxAmount: e.target.value }))}
                placeholder="∞"
                className="w-full px-3 py-1.5 text-sm border rounded focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        )}
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
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 border-b">
                <tr>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase cursor-pointer hover:bg-slate-100"
                    onClick={() => handleSort('timestamp')}
                  >
                    <div className="flex items-center gap-1">
                      Date <SortIcon field="timestamp" />
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase cursor-pointer hover:bg-slate-100"
                    onClick={() => handleSort('tx_type')}
                  >
                    <div className="flex items-center gap-1">
                      Type <SortIcon field="tx_type" />
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase cursor-pointer hover:bg-slate-100"
                    onClick={() => handleSort('asset')}
                  >
                    <div className="flex items-center gap-1">
                      Asset <SortIcon field="asset" />
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-right text-xs font-medium text-slate-500 uppercase cursor-pointer hover:bg-slate-100"
                    onClick={() => handleSort('amount')}
                  >
                    <div className="flex items-center justify-end gap-1">
                      Amount <SortIcon field="amount" />
                    </div>
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase">From/To</th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase cursor-pointer hover:bg-slate-100"
                    onClick={() => handleSort('wallet_label')}
                  >
                    <div className="flex items-center gap-1">
                      Wallet <SortIcon field="wallet_label" />
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-slate-500 uppercase cursor-pointer hover:bg-slate-100"
                    onClick={() => handleSort('tax_category')}
                  >
                    <div className="flex items-center gap-1">
                      Tax Category <SortIcon field="tax_category" />
                    </div>
                  </th>
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
                      {getTaxCategoryDisplay(tx.tax_category)}
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
        {pagination.totalPages > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-3 border-t bg-slate-50">
            {/* Page size selector */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-500">Show</span>
              <select
                value={pageSize}
                onChange={(e) => setPageSize(parseInt(e.target.value))}
                className="px-2 py-1 border rounded text-sm focus:ring-2 focus:ring-blue-500"
              >
                {PAGE_SIZES.map(size => (
                  <option key={size} value={size}>{size}</option>
                ))}
              </select>
              <span className="text-sm text-slate-500">per page</span>
            </div>

            {/* Page info */}
            <p className="text-sm text-slate-500">
              Showing {((pagination.page - 1) * pagination.limit) + 1} to{' '}
              {Math.min(pagination.page * pagination.limit, pagination.total)} of {pagination.total.toLocaleString()}
            </p>

            {/* Navigation */}
            <div className="flex items-center gap-2">
              {/* First page */}
              <button
                onClick={() => fetchTransactions(1)}
                disabled={pagination.page <= 1}
                className="p-2 border rounded-lg hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
                title="First page"
              >
                <ChevronsLeft className="w-4 h-4" />
              </button>
              
              {/* Previous page */}
              <button
                onClick={() => fetchTransactions(pagination.page - 1)}
                disabled={pagination.page <= 1}
                className="p-2 border rounded-lg hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
                title="Previous page"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>

              {/* Page input */}
              <form onSubmit={handleGoToPage} className="flex items-center gap-1">
                <span className="text-sm text-slate-500">Page</span>
                <input
                  type="number"
                  min={1}
                  max={pagination.totalPages}
                  value={goToPage || pagination.page}
                  onChange={(e) => setGoToPage(e.target.value)}
                  onFocus={(e) => e.target.select()}
                  className="w-16 px-2 py-1 border rounded text-sm text-center focus:ring-2 focus:ring-blue-500"
                />
                <span className="text-sm text-slate-500">of {pagination.totalPages}</span>
              </form>

              {/* Next page */}
              <button
                onClick={() => fetchTransactions(pagination.page + 1)}
                disabled={pagination.page >= pagination.totalPages}
                className="p-2 border rounded-lg hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
                title="Next page"
              >
                <ChevronRight className="w-4 h-4" />
              </button>

              {/* Last page */}
              <button
                onClick={() => fetchTransactions(pagination.totalPages)}
                disabled={pagination.page >= pagination.totalPages}
                className="p-2 border rounded-lg hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed"
                title="Last page"
              >
                <ChevronsRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

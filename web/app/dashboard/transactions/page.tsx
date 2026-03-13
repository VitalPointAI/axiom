'use client';

import { useState, useEffect, useCallback } from 'react';
import { apiClient, ApiError } from '@/lib/api';
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
  X,
  Globe
} from 'lucide-react';

interface Transaction {
  id: string;
  wallet_id: number;
  tx_hash: string;
  timestamp: string;
  tx_type: string;
  from_address: string;
  to_address: string;
  asset: string;
  amount: number;
  fee: number;
  chain: string;
  chain_name: string;
  explorer_url: string;
  wallet_label: string;
  tax_category: string;
  needs_review: boolean;
}

interface Pagination {
  page: number;
  per_page: number;
  total: number;
  pages: number;
}

interface ChainOption {
  value: string;
  label: string;
}

interface Filters {
  types: string[];
  chains: ChainOption[];
  categories: string[];
  assets: string[];
}

type SortField = 'timestamp' | 'tx_type' | 'asset' | 'amount' | 'tax_category' | 'wallet_label' | 'chain';
type SortDir = 'asc' | 'desc';

const TAX_CATEGORY_CONFIG: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  'transfer': { label: 'Transfer', color: 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-900/30', icon: <ArrowLeftRight className="w-3 h-3" /> },
  'staking': { label: 'Staking', color: 'text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-900/30', icon: <Landmark className="w-3 h-3" /> },
  'unstaking': { label: 'Unstaking', color: 'text-yellow-600 bg-yellow-50 dark:text-yellow-400 dark:bg-yellow-900/30', icon: <ArrowUpRight className="w-3 h-3" /> },
  'swap': { label: 'Swap', color: 'text-purple-600 bg-purple-50 dark:text-purple-400 dark:bg-purple-900/30', icon: <RefreshCw className="w-3 h-3" /> },
  'defi-lending': { label: 'DeFi Lending', color: 'text-cyan-600 bg-cyan-50 dark:text-cyan-400 dark:bg-cyan-900/30', icon: <Coins className="w-3 h-3" /> },
  'liquid-staking': { label: 'Liquid Staking', color: 'text-teal-600 bg-teal-50 dark:text-teal-400 dark:bg-teal-900/30', icon: <Zap className="w-3 h-3" /> },
  'nft': { label: 'NFT', color: 'text-pink-600 bg-pink-50 dark:text-pink-400 dark:bg-pink-900/30', icon: <Palette className="w-3 h-3" /> },
  'contract-call': { label: 'Contract Call', color: 'text-slate-600 bg-slate-100 dark:text-slate-400 dark:bg-slate-700', icon: <FileText className="w-3 h-3" /> },
  'uncategorized': { label: 'Uncategorized', color: 'text-gray-500 bg-gray-50 dark:text-gray-400 dark:bg-gray-800', icon: <ArrowDownRight className="w-3 h-3" /> },
};

const CHAIN_COLORS: Record<string, string> = {
  'near': 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  'ethereum': 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  'polygon': 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  'optimism': 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  'arbitrum': 'bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400',
  'base': 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400',
};

const PAGE_SIZES = [10, 25, 50, 100];

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [pagination, setPagination] = useState<Pagination>({ page: 1, per_page: 25, total: 0, pages: 0 });
  const [filters, setFilters] = useState<Filters>({ types: [], chains: [], categories: [], assets: [] });
  const [loading, setLoading] = useState(true);

  // Filter state
  const [selectedType, setSelectedType] = useState('');
  const [selectedChain, setSelectedChain] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [selectedAsset, setSelectedAsset] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
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

  interface TransactionsResponse {
    transactions: Transaction[];
    total: number;
    page: number;
    per_page: number;
    pages: number;
  }

  const fetchTransactions = useCallback(async (page = 1) => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        page: page.toString(),
        per_page: pageSize.toString(),
      });

      if (selectedType) params.set('tx_type', selectedType);
      if (selectedChain) params.set('chain', selectedChain);
      if (selectedCategory) params.set('tax_category', selectedCategory);
      if (selectedAsset) params.set('asset', selectedAsset);
      if (searchQuery) params.set('q', searchQuery);
      if (startDate) params.set('date_from', startDate);
      if (endDate) params.set('date_to', endDate);
      if (columnFilters.wallet) params.set('wallet', columnFilters.wallet);

      const data = await apiClient.get<TransactionsResponse>(`/api/transactions?${params}`);

      setTransactions(data.transactions || []);
      setPagination({
        page: data.page || 1,
        per_page: data.per_page || pageSize,
        total: data.total || 0,
        pages: data.pages || 0,
      });
    } catch (error) {
      console.error('Failed to fetch transactions:', error);
    } finally {
      setLoading(false);
    }
  }, [pageSize, sortField, sortDir, selectedType, selectedChain, selectedCategory, selectedAsset, searchQuery, columnFilters, startDate, endDate]);

  useEffect(() => {
    fetchTransactions(1);
  }, [pageSize, sortField, sortDir, selectedType, selectedChain, selectedCategory, selectedAsset, startDate, endDate]);

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
    if (page >= 1 && page <= pagination.pages) {
      fetchTransactions(page);
      setGoToPage('');
    }
  };

  // Export is not available via FastAPI yet — show informative message
  const handleExport = () => {
    alert('CSV export will be available once the full report package is generated in the Reports tab.');
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUp className="w-3 h-3 opacity-30" />;
    return sortDir === 'asc' 
      ? <ArrowUp className="w-3 h-3 text-blue-500" />
      : <ArrowDown className="w-3 h-3 text-blue-500" />;
  };

  const getTypeIcon = (type: string) => {
    switch (type?.toLowerCase()) {
      case 'transfer': return <ArrowLeftRight className="w-4 h-4" />;
      case 'stake':
      case 'unstake': return <ArrowUpRight className="w-4 h-4" />;
      case 'erc20': return <Coins className="w-4 h-4" />;
      case 'nft': return <Palette className="w-4 h-4" />;
      case 'internal': return <Zap className="w-4 h-4" />;
      default: return <ArrowDownRight className="w-4 h-4" />;
    }
  };

  const getTypeColor = (type: string) => {
    switch (type?.toLowerCase()) {
      case 'transfer': return 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-900/30';
      case 'stake': return 'text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-900/30';
      case 'unstake': return 'text-orange-600 bg-orange-50 dark:text-orange-400 dark:bg-orange-900/30';
      case 'swap': return 'text-purple-600 bg-purple-50 dark:text-purple-400 dark:bg-purple-900/30';
      case 'erc20': return 'text-cyan-600 bg-cyan-50 dark:text-cyan-400 dark:bg-cyan-900/30';
      case 'nft': return 'text-pink-600 bg-pink-50 dark:text-pink-400 dark:bg-pink-900/30';
      case 'internal': return 'text-yellow-600 bg-yellow-50 dark:text-yellow-400 dark:bg-yellow-900/30';
      default: return 'text-slate-600 bg-slate-50 dark:text-slate-400 dark:bg-slate-700';
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
    setSelectedChain('');
    setSelectedCategory('');
    setSelectedAsset('');
    setStartDate('');
    setEndDate('');
    setSearchQuery('');
    setColumnFilters({ wallet: '', address: '', minAmount: '', maxAmount: '' });
    fetchTransactions(1);
  };

  const hasActiveFilters = selectedType || selectedChain || selectedCategory || selectedAsset || searchQuery || 
    columnFilters.wallet || columnFilters.address || columnFilters.minAmount || columnFilters.maxAmount || startDate || endDate;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Transactions</h1>
          <p className="text-slate-500 dark:text-slate-400">{pagination.total.toLocaleString()} total transactions</p>
        </div>
        <button 
          onClick={handleExport}
          className="flex items-center gap-2 px-4 py-2 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition text-slate-700 dark:text-slate-300"
        >
          <Download className="w-4 h-4" />
          Export CSV
        </button>
      </div>

      {/* Filters Bar */}
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-4">
        <div className="flex flex-wrap items-center gap-3">
          {/* Search */}
          <form onSubmit={handleSearch} className="flex-1 min-w-[200px]">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by hash, address..."
                className="w-full pl-10 pr-4 py-2 border border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-white placeholder-slate-400 focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
          </form>

          {/* Asset filter */}
          <select
            value={selectedAsset}
            onChange={(e) => setSelectedAsset(e.target.value)}
            className="px-3 py-2 border border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Assets</option>
            {filters.assets.map(asset => (
              <option key={asset} value={asset}>{asset}</option>
            ))}
          </select>

          {/* Chain filter */}
          <select
            value={selectedChain}
            onChange={(e) => setSelectedChain(e.target.value)}
            className="px-3 py-2 border border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Chains</option>
            {filters.chains.map(chain => (
              <option key={chain.value} value={chain.value}>{chain.label}</option>
            ))}
          </select>

          {/* Type filter */}
          <select
            value={selectedType}
            onChange={(e) => setSelectedType(e.target.value)}
            className="px-3 py-2 border border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Types</option>
            {filters.types.map(type => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>

          {/* Date filters */}
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="px-3 py-2 border border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500 text-sm"
              title="From date"
            />
            <span className="text-gray-400">to</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="px-3 py-2 border border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500 text-sm"
              title="To date"
            />
          </div>

          {/* Category filter */}
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            className="px-3 py-2 border border-slate-200 dark:border-slate-600 rounded-lg bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All Categories</option>
            {Object.entries(TAX_CATEGORY_CONFIG).map(([key, config]) => (
              <option key={key} value={key}>{config.label}</option>
            ))}
          </select>

          {/* Column Filters Toggle */}
          <button
            onClick={() => setShowColumnFilters(!showColumnFilters)}
            className={`flex items-center gap-2 px-3 py-2 border rounded-lg transition ${showColumnFilters ? 'bg-blue-50 dark:bg-blue-900/30 border-blue-200 dark:border-blue-700' : 'border-slate-200 dark:border-slate-600 hover:bg-slate-50 dark:hover:bg-slate-700'} text-slate-700 dark:text-slate-300`}
          >
            <Filter className="w-4 h-4" />
            More
          </button>

          {hasActiveFilters && (
            <button
              onClick={clearAllFilters}
              className="flex items-center gap-1 text-sm text-red-500 hover:text-red-700"
            >
              <X className="w-4 h-4" />
              Clear
            </button>
          )}
        </div>

        {/* Column Filters */}
        {showColumnFilters && (
          <div className="mt-4 pt-4 border-t border-slate-200 dark:border-slate-700 grid grid-cols-2 md:grid-cols-5 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Wallet</label>
              <input
                type="text"
                value={columnFilters.wallet}
                onChange={(e) => setColumnFilters(prev => ({ ...prev, wallet: e.target.value }))}
                placeholder="Filter by wallet..."
                className="w-full px-3 py-1.5 text-sm border border-slate-200 dark:border-slate-600 rounded bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Address</label>
              <input
                type="text"
                value={columnFilters.address}
                onChange={(e) => setColumnFilters(prev => ({ ...prev, address: e.target.value }))}
                placeholder="From/To address..."
                className="w-full px-3 py-1.5 text-sm border border-slate-200 dark:border-slate-600 rounded bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Min Amount</label>
              <input
                type="number"
                value={columnFilters.minAmount}
                onChange={(e) => setColumnFilters(prev => ({ ...prev, minAmount: e.target.value }))}
                placeholder="0"
                className="w-full px-3 py-1.5 text-sm border border-slate-200 dark:border-slate-600 rounded bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-500 dark:text-slate-400 mb-1">Max Amount</label>
              <input
                type="number"
                value={columnFilters.maxAmount}
                onChange={(e) => setColumnFilters(prev => ({ ...prev, maxAmount: e.target.value }))}
                placeholder="∞"
                className="w-full px-3 py-1.5 text-sm border border-slate-200 dark:border-slate-600 rounded bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex items-end">
              <button
                onClick={() => fetchTransactions(1)}
                className="w-full px-4 py-1.5 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700 transition"
              >
                Apply
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Transactions Table */}
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-400 mx-auto"></div>
          </div>
        ) : transactions.length === 0 ? (
          <div className="p-12 text-center text-slate-500 dark:text-slate-400">
            <ArrowLeftRight className="w-12 h-12 mx-auto mb-4 text-slate-300 dark:text-slate-600" />
            <p>No transactions found</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-slate-50 dark:bg-slate-900/50 border-b border-slate-200 dark:border-slate-700">
                <tr>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800"
                    onClick={() => handleSort('timestamp')}
                  >
                    <div className="flex items-center gap-1">
                      Date <SortIcon field="timestamp" />
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800"
                    onClick={() => handleSort('chain')}
                  >
                    <div className="flex items-center gap-1">
                      Chain <SortIcon field="chain" />
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800"
                    onClick={() => handleSort('tx_type')}
                  >
                    <div className="flex items-center gap-1">
                      Type <SortIcon field="tx_type" />
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800"
                    onClick={() => handleSort('asset')}
                  >
                    <div className="flex items-center gap-1">
                      Asset <SortIcon field="asset" />
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-right text-xs font-medium text-slate-500 dark:text-slate-400 uppercase cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800"
                    onClick={() => handleSort('amount')}
                  >
                    <div className="flex items-center justify-end gap-1">
                      Amount <SortIcon field="amount" />
                    </div>
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">From/To</th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800"
                    onClick={() => handleSort('wallet_label')}
                  >
                    <div className="flex items-center gap-1">
                      Wallet <SortIcon field="wallet_label" />
                    </div>
                  </th>
                  <th 
                    className="px-4 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-800"
                    onClick={() => handleSort('tax_category')}
                  >
                    <div className="flex items-center gap-1">
                      Category <SortIcon field="tax_category" />
                    </div>
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-slate-500 dark:text-slate-400 uppercase">Hash</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                {transactions.map((tx) => (
                  <tr key={tx.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/50">
                    <td className="px-4 py-3 text-sm text-slate-600 dark:text-slate-300">
                      {new Date(tx.timestamp).toLocaleDateString()}
                      <br />
                      <span className="text-xs text-slate-400">
                        {new Date(tx.timestamp).toLocaleTimeString()}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${CHAIN_COLORS[tx.chain] || 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'}`}>
                        <Globe className="w-3 h-3" />
                        {tx.chain_name || tx.chain}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${getTypeColor(tx.tx_type)}`}>
                        {getTypeIcon(tx.tx_type)}
                        {tx.tx_type || 'unknown'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm font-medium text-slate-800 dark:text-slate-200">
                      {tx.asset}
                    </td>
                    <td className="px-4 py-3 text-sm text-right font-mono text-slate-900 dark:text-slate-100">
                      {tx.amount?.toLocaleString(undefined, { maximumFractionDigits: 6 })}
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-600 dark:text-slate-400 font-mono">
                      <div title={tx.from_address}>{formatAddress(tx.from_address)}</div>
                      <div className="text-xs text-slate-400">→ {formatAddress(tx.to_address)}</div>
                    </td>
                    <td className="px-4 py-3 text-sm text-slate-600 dark:text-slate-400">
                      {tx.wallet_label || '-'}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      {getTaxCategoryDisplay(tx.tax_category)}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <a
                        href={tx.explorer_url || `https://nearblocks.io/txns/${tx.tx_hash}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-blue-500 hover:underline font-mono"
                      >
                        {tx.tx_hash?.slice(0, 8)}...
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
        {pagination.pages > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-3 border-t border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50">
            {/* Page size selector */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-500 dark:text-slate-400">Show</span>
              <select
                value={pageSize}
                onChange={(e) => setPageSize(parseInt(e.target.value))}
                className="px-2 py-1 border border-slate-200 dark:border-slate-600 rounded text-sm bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500"
              >
                {PAGE_SIZES.map(size => (
                  <option key={size} value={size}>{size}</option>
                ))}
              </select>
              <span className="text-sm text-slate-500 dark:text-slate-400">per page</span>
            </div>

            {/* Page info */}
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Showing {((pagination.page - 1) * pagination.per_page) + 1} to{' '}
              {Math.min(pagination.page * pagination.per_page, pagination.total)} of {pagination.total.toLocaleString()}
            </p>

            {/* Navigation */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => fetchTransactions(1)}
                disabled={pagination.page <= 1}
                className="p-2 border border-slate-200 dark:border-slate-600 rounded-lg hover:bg-white dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed text-slate-700 dark:text-slate-300"
                title="First page"
              >
                <ChevronsLeft className="w-4 h-4" />
              </button>
              
              <button
                onClick={() => fetchTransactions(pagination.page - 1)}
                disabled={pagination.page <= 1}
                className="p-2 border border-slate-200 dark:border-slate-600 rounded-lg hover:bg-white dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed text-slate-700 dark:text-slate-300"
                title="Previous page"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>

              <form onSubmit={handleGoToPage} className="flex items-center gap-1">
                <span className="text-sm text-slate-500 dark:text-slate-400">Page</span>
                <input
                  type="number"
                  min={1}
                  max={pagination.pages}
                  value={goToPage || pagination.page}
                  onChange={(e) => setGoToPage(e.target.value)}
                  onFocus={(e) => e.target.select()}
                  className="w-16 px-2 py-1 border border-slate-200 dark:border-slate-600 rounded text-sm text-center bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-blue-500"
                />
                <span className="text-sm text-slate-500 dark:text-slate-400">of {pagination.pages}</span>
              </form>

              <button
                onClick={() => fetchTransactions(pagination.page + 1)}
                disabled={pagination.page >= pagination.pages}
                className="p-2 border border-slate-200 dark:border-slate-600 rounded-lg hover:bg-white dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed text-slate-700 dark:text-slate-300"
                title="Next page"
              >
                <ChevronRight className="w-4 h-4" />
              </button>

              <button
                onClick={() => fetchTransactions(pagination.pages)}
                disabled={pagination.page >= pagination.pages}
                className="p-2 border border-slate-200 dark:border-slate-600 rounded-lg hover:bg-white dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed text-slate-700 dark:text-slate-300"
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

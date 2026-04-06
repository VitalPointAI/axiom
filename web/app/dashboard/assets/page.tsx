'use client';

import { useState, useEffect, useCallback } from 'react';
import { 
  Coins, Search, Download, ChevronDown, ChevronRight, Globe, Wallet, X,
  RefreshCw, Ban, MoreVertical, AlertTriangle, Calendar, Clock
} from 'lucide-react';

interface WalletHolding {
  address: string;
  label: string;
  balance: number;
  value_usd: number;
}

interface Asset {
  asset: string;
  chain: string;
  chain_name: string;
  balance: number;
  price_usd: number;
  value_usd: number;
  contract?: string;
  is_spam?: boolean;
  pending_balance?: boolean;
  token_name?: string;
  icon_url?: string;
  wallets: WalletHolding[];
}

interface ChainOption { value: string; label: string; }
interface Filters { chains: ChainOption[]; assets: string[]; wallets: string[]; }

const CHAIN_COLORS: Record<string, string> = {
  'near': 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300',
  'NEAR': 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300',
  'ethereum': 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  'ETH': 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  'xrp': 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
};

const ASSET_ICONS: Record<string, string> = {
  'NEAR': '🌐', 'ETH': '💎', 'MATIC': '💜', 'USDC': '💵', 'USDT': '💵',
  'WETH': '💎', 'WNEAR': '🌐', 'XRP': '✕', 'CRO': '🔷',
};

export default function AssetsPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [totalValueUsd, setTotalValueUsd] = useState(0);
  const [filters, setFilters] = useState<Filters>({ chains: [], assets: [], wallets: [] });
  const [snapshotDates, setSnapshotDates] = useState<string[]>([]);
  const [isHistorical, setIsHistorical] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expandedAssets, setExpandedAssets] = useState<Set<string>>(new Set());
  const [openMenu, setOpenMenu] = useState<string | null>(null);

  // Filter state
  const [selectedChain, setSelectedChain] = useState('');
  const [selectedAsset, setSelectedAsset] = useState('');
  const [walletSearch, setWalletSearch] = useState('');
  const [hideSmall, setHideSmall] = useState(true);
  const [showSpam, setShowSpam] = useState(false);
  const [selectedDate, setSelectedDate] = useState(''); // YYYY-MM-DD or empty for live

  const fetchAssets = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (selectedChain) params.set('chain', selectedChain);
      if (selectedAsset) params.set('asset', selectedAsset);
      if (walletSearch) params.set('wallet', walletSearch);
      if (selectedDate) params.set('date', selectedDate);
      params.set('hideSmall', hideSmall.toString());
      params.set('includeSpam', showSpam.toString());

      const res = await fetch(`/api/assets?${params}`);
      const data = await res.json();
      
      setAssets(data.assets || []);
      setTotalValueUsd(data.totalValueUsd || 0);
      setFilters(data.filters || { chains: [], assets: [], wallets: [] });
      setSnapshotDates(data.snapshotDates || []);
      setIsHistorical(data.isHistorical || false);
    } catch (error) {
      console.error('Failed to fetch assets:', error);
    } finally {
      setLoading(false);
    }
  }, [selectedChain, selectedAsset, walletSearch, hideSmall, showSpam, selectedDate]);

  useEffect(() => {
    fetchAssets();
  }, [selectedChain, selectedAsset, hideSmall, showSpam, selectedDate]);

  const handleWalletSearch = (e: React.FormEvent) => {
    e.preventDefault();
    fetchAssets();
  };

  const toggleExpand = (assetKey: string) => {
    const newExpanded = new Set(expandedAssets);
    if (newExpanded.has(assetKey)) newExpanded.delete(assetKey);
    else newExpanded.add(assetKey);
    setExpandedAssets(newExpanded);
  };

  const clearAllFilters = () => {
    setSelectedChain('');
    setSelectedAsset('');
    setWalletSearch('');
    setHideSmall(true);
    setShowSpam(false);
    setSelectedDate('');
  };

  const hasActiveFilters = selectedChain || selectedAsset || walletSearch || !hideSmall || showSpam || selectedDate;

  const handleMarkAsSpam = async (asset: Asset) => {
    try {
      const res = await fetch('/api/assets/spam', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token_symbol: asset.asset, token_contract: asset.contract, reason: 'User marked as spam' }),
      });
      if (res.ok) { fetchAssets(); setOpenMenu(null); }
    } catch (error) { console.error('Failed to mark as spam:', error); }
  };

  const handleUnmarkSpam = async (asset: Asset) => {
    try {
      const res = await fetch(`/api/assets/spam?token_symbol=${encodeURIComponent(asset.asset)}`, { method: 'DELETE' });
      if (res.ok) { fetchAssets(); setOpenMenu(null); }
    } catch (error) { console.error('Failed to unmark spam:', error); }
  };

  const handleExport = async () => {
    const rows = [['Asset', 'Chain', 'Balance', 'Price USD', 'Value USD', 'Wallets'].join(',')];
    for (const asset of assets) {
      const walletList = asset.wallets.map(w => w.label || w.address).join('; ');
      rows.push([asset.asset, asset.chain_name, asset.balance.toFixed(6), asset.price_usd.toFixed(2), asset.value_usd.toFixed(2), `"${walletList}"`].join(','));
    }
    const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `neartax-assets-${selectedDate || 'live'}-${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  const formatBalance = (balance: number) => {
    if (balance >= 1000000) return `${(balance / 1000000).toFixed(2)}M`;
    if (balance >= 1000) return `${(balance / 1000).toFixed(2)}K`;
    return balance.toLocaleString(undefined, { maximumFractionDigits: 4 });
  };

  const formatUsd = (value: number) => {
    if (value >= 1000000) return `$${(value / 1000000).toFixed(2)}M`;
    if (value >= 1000) return `$${(value / 1000).toFixed(2)}K`;
    return `$${value.toFixed(2)}`;
  };

  useEffect(() => {
    const handleClickOutside = () => setOpenMenu(null);
    if (openMenu) {
      document.addEventListener('click', handleClickOutside);
      return () => document.removeEventListener('click', handleClickOutside);
    }
  }, [openMenu]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
            Assets
            {isHistorical && (
              <span className="text-sm font-normal bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-300 px-2 py-0.5 rounded flex items-center gap-1">
                <Clock className="w-3 h-3" />
                Historical: {selectedDate}
              </span>
            )}
          </h1>
          <p className="text-slate-500 dark:text-slate-400">
            {assets.length} assets · Total: <span className="font-semibold text-slate-700 dark:text-slate-200">{formatUsd(totalValueUsd)}</span>
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={fetchAssets} className="flex items-center gap-2 px-3 py-2 border border-slate-300 dark:border-slate-600 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700" title="Refresh">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button onClick={handleExport} className="flex items-center gap-2 px-4 py-2 border border-slate-300 dark:border-slate-600 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700">
            <Download className="w-4 h-4" /> Export CSV
          </button>
        </div>
      </div>

      {/* Filters Bar */}
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-4">
        <div className="flex flex-wrap items-center gap-3">
          {/* Date filter */}
          <div className="flex items-center gap-2">
            <Calendar className="w-4 h-4 text-slate-400" />
            <select
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              className="px-3 py-2 border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500"
            >
              <option value="">Live (Current)</option>
              {snapshotDates.map(date => (
                <option key={date} value={date}>{date}</option>
              ))}
            </select>
          </div>

          {/* Asset filter */}
          <select value={selectedAsset} onChange={(e) => setSelectedAsset(e.target.value)}
            className="px-3 py-2 border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500">
            <option value="">All Assets</option>
            {filters.assets.map(asset => (<option key={asset} value={asset}>{asset}</option>))}
          </select>

          {/* Chain filter */}
          <select value={selectedChain} onChange={(e) => setSelectedChain(e.target.value)}
            className="px-3 py-2 border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500">
            <option value="">All Chains</option>
            {filters.chains.map(chain => (<option key={chain.value} value={chain.value}>{chain.label}</option>))}
          </select>

          {/* Wallet search */}
          <form onSubmit={handleWalletSearch} className="flex-1 min-w-[200px] max-w-sm">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
              <input type="text" value={walletSearch} onChange={(e) => setWalletSearch(e.target.value)} placeholder="Search wallet..."
                className="w-full pl-10 pr-4 py-2 border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500" />
            </div>
          </form>

          {/* Toggles */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={hideSmall} onChange={(e) => setHideSmall(e.target.checked)} className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500" />
            <span className="text-sm text-slate-600 dark:text-slate-300">Hide &lt;$1</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={showSpam} onChange={(e) => setShowSpam(e.target.checked)} className="w-4 h-4 rounded border-gray-300 text-orange-600 focus:ring-orange-500" />
            <span className="text-sm text-slate-600 dark:text-slate-300">Show spam</span>
          </label>

          {hasActiveFilters && (
            <button onClick={clearAllFilters} className="flex items-center gap-1 text-sm text-red-500 hover:text-red-700">
              <X className="w-4 h-4" /> Clear
            </button>
          )}
        </div>
      </div>

      {/* Assets List */}
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 overflow-hidden">
        {loading ? (
          <div className="p-8 text-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-slate-400 mx-auto"></div></div>
        ) : assets.length === 0 ? (
          <div className="p-12 text-center text-slate-500 dark:text-slate-400">
            <Coins className="w-12 h-12 mx-auto mb-4 text-slate-300 dark:text-slate-600" />
            <p>No assets found</p>
            {hideSmall && <p className="text-sm mt-2">Try unchecking "Hide &lt;$1" to see all assets</p>}
            {selectedDate && <p className="text-sm mt-2">No snapshot data for {selectedDate}</p>}
          </div>
        ) : (
          <div className="divide-y divide-slate-200 dark:divide-slate-700">
            {assets.map((asset) => {
              const assetKey = `${asset.asset}-${asset.chain}`;
              const isExpanded = expandedAssets.has(assetKey);
              
              return (
                <div key={assetKey}>
                  <div className={`flex items-center gap-4 p-4 hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer ${asset.is_spam ? 'opacity-60' : ''}`}>
                    <div className="w-5 h-5 flex items-center justify-center text-slate-400" onClick={() => toggleExpand(assetKey)}>
                      {asset.wallets.length > 1 ? (isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />) : <span className="w-4" />}
                    </div>

                    <div className="flex items-center gap-3 min-w-[140px]" onClick={() => toggleExpand(assetKey)}>
                      <div className="w-10 h-10 rounded-full bg-slate-100 dark:bg-slate-700 flex items-center justify-center text-xl overflow-hidden">
                        {asset.is_spam ? <AlertTriangle className="w-5 h-5 text-orange-500" /> :
                          asset.icon_url ? <img src={asset.icon_url} alt={asset.asset} className="w-10 h-10 rounded-full" /> :
                          (ASSET_ICONS[asset.asset] || '🪙')}
                      </div>
                      <div>
                        <div className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                          {asset.asset}
                          {asset.pending_balance && <span className="text-xs bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300 px-1.5 py-0.5 rounded">Syncing</span>}
                          {asset.is_spam && <span className="text-xs bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300 px-1.5 py-0.5 rounded">SPAM</span>}
                        </div>
                        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium ${CHAIN_COLORS[asset.chain] || 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'}`}>
                          <Globe className="w-3 h-3" /> {asset.chain_name}
                        </span>
                      </div>
                    </div>

                    <div className="flex-1 text-right" onClick={() => toggleExpand(assetKey)}>
                      <div className="font-mono text-slate-900 dark:text-white">{formatBalance(asset.balance)}</div>
                      <div className="text-xs text-slate-400">{asset.wallets.length} wallet{asset.wallets.length > 1 ? 's' : ''}</div>
                    </div>

                    <div className="w-24 text-right" onClick={() => toggleExpand(assetKey)}>
                      <div className="text-sm text-slate-600 dark:text-slate-300">{asset.price_usd > 0 ? formatUsd(asset.price_usd) : '-'}</div>
                    </div>

                    <div className="w-32 text-right" onClick={() => toggleExpand(assetKey)}>
                      <div className="font-semibold text-slate-900 dark:text-white">{formatUsd(asset.value_usd)}</div>
                      {totalValueUsd > 0 && <div className="text-xs text-slate-400">{((asset.value_usd / totalValueUsd) * 100).toFixed(1)}%</div>}
                    </div>

                    <div className="relative">
                      <button onClick={(e) => { e.stopPropagation(); setOpenMenu(openMenu === assetKey ? null : assetKey); }}
                        className="p-2 hover:bg-slate-100 dark:hover:bg-slate-600 rounded-lg">
                        <MoreVertical className="w-4 h-4 text-slate-400" />
                      </button>
                      
                      {openMenu === assetKey && (
                        <div className="absolute right-0 top-full mt-1 w-48 bg-white dark:bg-slate-700 rounded-lg shadow-lg border border-slate-200 dark:border-slate-600 py-1 z-10">
                          {asset.is_spam ? (
                            <button onClick={(e) => { e.stopPropagation(); handleUnmarkSpam(asset); }}
                              className="w-full px-4 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-600 flex items-center gap-2 text-green-600 dark:text-green-400">
                              <Ban className="w-4 h-4" /> Unmark as spam
                            </button>
                          ) : (
                            <button onClick={(e) => { e.stopPropagation(); handleMarkAsSpam(asset); }}
                              className="w-full px-4 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-600 flex items-center gap-2 text-orange-600 dark:text-orange-400">
                              <Ban className="w-4 h-4" /> Mark as spam
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {isExpanded && asset.wallets.length > 1 && (
                    <div className="bg-slate-50 dark:bg-slate-900 border-t border-slate-200 dark:border-slate-700">
                      {asset.wallets.map((wallet, idx) => (
                        <div key={idx} className="flex items-center gap-4 px-4 py-2 pl-14 text-sm">
                          <Wallet className="w-4 h-4 text-slate-400" />
                          <div className="flex-1 min-w-0">
                            <span className="font-medium text-slate-700 dark:text-slate-300">{wallet.label || wallet.address.slice(0, 12) + '...'}</span>
                            {wallet.label && <span className="ml-2 text-slate-400 font-mono text-xs">{wallet.address.slice(0, 8)}...{wallet.address.slice(-6)}</span>}
                          </div>
                          <div className="font-mono text-slate-600 dark:text-slate-300">{formatBalance(wallet.balance)}</div>
                          <div className="w-32 text-right text-slate-600 dark:text-slate-300">{formatUsd(wallet.value_usd)}</div>
                          <div className="w-10"></div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Summary Cards */}
      {!loading && assets.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-4">
            <div className="text-sm text-slate-500 dark:text-slate-400 mb-1">Total Value</div>
            <div className="text-2xl font-bold text-slate-900 dark:text-white">{formatUsd(totalValueUsd)}</div>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-4">
            <div className="text-sm text-slate-500 dark:text-slate-400 mb-1">Top Asset</div>
            <div className="text-2xl font-bold text-slate-900 dark:text-white">{assets[0]?.asset || '-'}</div>
            <div className="text-sm text-slate-400">{assets[0] && totalValueUsd > 0 ? `${((assets[0].value_usd / totalValueUsd) * 100).toFixed(1)}% of portfolio` : ''}</div>
          </div>
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-4">
            <div className="text-sm text-slate-500 dark:text-slate-400 mb-1">Assets Tracked</div>
            <div className="text-2xl font-bold text-slate-900 dark:text-white">{assets.length}</div>
            <div className="text-sm text-slate-400">Across {new Set(assets.map(a => a.chain)).size} chains</div>
          </div>
        </div>
      )}
    </div>
  );
}

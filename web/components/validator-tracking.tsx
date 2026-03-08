'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { 
  TrendingUp, Plus, Trash2, ExternalLink, Loader2, 
  ChevronDown, ChevronUp, Crown, Filter, Download, Info
} from 'lucide-react';
import { formatNumber } from '@/lib/utils';

interface ValidatorMeta {
  name?: string;
  url?: string;
  logo?: string;
}

interface ValidatorStats {
  poolId: string;
  label: string | null;
  isOwner: boolean;
  meta: ValidatorMeta;
  totalStakedNear: number;
  delegatorCount: number;
  ownStake: number;
  ownStakeByWallet: { account: string; staked: number }[];
  commissionRate: number;
  isActive: boolean;
}

interface StakingActivity {
  date: string;
  type: "deposit" | "withdrawal" | "reward";
  epochTime?: string;
  amount_near: number;
  price_usd: number;
  value_usd: number;
  cumulative_stake: number;
  timestamp: number;
  wallet?: string;
  tx_hash?: string;
  stakeAtEpoch?: number;
}

interface AllTimeTotals {
  totalDeposits: number;
  totalWithdrawals: number;
  netDeposits: number;
  currentStake: number;
  accumulatedRewards: number;
  accumulatedRewardsUsd: number;
  depositCount: number;
  withdrawalCount: number;
  epochCount: number;
}

interface PeriodTotals {
  totalDeposits: number;
  totalWithdrawals: number;
  totalRewards: number;
  totalRewardsUsd: number;
  depositCount: number;
  withdrawalCount: number;
  epochCount: number;
  dateRange: { from: string | null; to: string | null };
}

interface ValidatorResponse {
  validators: ValidatorStats[];
  totals: { totalStaked: number };
}

interface ValidatorDetailResponse {
  validator: ValidatorStats;
  stakingActivity: StakingActivity[];
  periodTotals: PeriodTotals;
  allTimeTotals: AllTimeTotals;
  isOwner: boolean;
}

type DateFilter = 'day' | 'week' | 'month' | 'year' | 'all' | 'custom';
type ActivityFilter = 'all' | 'deposit' | 'withdrawal' | 'reward';

export function ValidatorTracking() {
  const [validators, setValidators] = useState<ValidatorStats[]>([]);
  const [totals, setTotals] = useState<{ totalStaked: number } | null>(null);
  const [loading, setLoading] = useState(true);
  const [newPoolId, setNewPoolId] = useState('');
  const [isOwnerNew, setIsOwnerNew] = useState(false);
  const [adding, setAdding] = useState(false);
  const [expandedValidator, setExpandedValidator] = useState<string | null>(null);
  const [detailData, setDetailData] = useState<ValidatorDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [dateFilter, setDateFilter] = useState<DateFilter>('all');
  const [activityFilter, setActivityFilter] = useState<ActivityFilter>('all');
  const [customStartDate, setCustomStartDate] = useState<string>('');
  const [customEndDate, setCustomEndDate] = useState<string>('');

  useEffect(() => {
    fetchValidators();
  }, []);

  const fetchValidators = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/validators');
      if (!res.ok) throw new Error('Failed to fetch');
      const data: ValidatorResponse = await res.json();
      setValidators(data.validators || []);
      setTotals(data.totals);
    } catch {
      console.error('Failed to load validators');
    } finally {
      setLoading(false);
    }
  };

  const fetchValidatorDetail = async (poolId: string, filter: DateFilter, startDate?: string, endDate?: string) => {
    try {
      setDetailLoading(true);
      let filterParam = filter === 'all' ? '' : `&dateFilter=${filter}`;
      if (filter === 'custom' && startDate && endDate) {
        filterParam = `&startDate=${startDate}&endDate=${endDate}`;
      }
      const res = await fetch(`/api/validators?poolId=${encodeURIComponent(poolId)}${filterParam}`);
      if (!res.ok) throw new Error('Failed to load');
      const data: ValidatorDetailResponse = await res.json();
      setDetailData(data);
    } catch (err) {
      console.error('Error:', err);
    } finally {
      setDetailLoading(false);
    }
  };

  const toggleExpand = async (poolId: string) => {
    if (expandedValidator === poolId) {
      setExpandedValidator(null);
      setDetailData(null);
    } else {
      setExpandedValidator(poolId);
      await fetchValidatorDetail(poolId, dateFilter, customStartDate, customEndDate);
    }
  };

  const handleDateFilterChange = async (filter: DateFilter) => {
    setDateFilter(filter);
    if (expandedValidator) {
      await fetchValidatorDetail(expandedValidator, filter, customStartDate, customEndDate);
    }
  };

  const applyCustomDateFilter = async () => {
    if (customStartDate && customEndDate && expandedValidator) {
      setDateFilter('custom');
      await fetchValidatorDetail(expandedValidator, 'custom', customStartDate, customEndDate);
    }
  };

  const exportToKoinlyCsv = () => {
    if (!detailData?.stakingActivity?.length) return;
    
    const filtered = activityFilter === 'all' 
      ? detailData.stakingActivity 
      : detailData.stakingActivity.filter(a => a.type === activityFilter);
    
    const headers = [
      "Date", "Sent Amount", "Sent Currency", "Received Amount", "Received Currency",
      "Fee Amount", "Fee Currency", "Net Worth Amount", "Net Worth Currency",
      "Label", "Description", "TxHash"
    ];
    
    const rows = filtered.map(a => {
      const isIncoming = a.type === 'deposit' || a.type === 'reward';
      const label = a.type === 'reward' ? 'staking' : a.type;
      const time = a.epochTime || '00:00';
      const desc = a.type === 'reward' 
        ? `Epoch reward @ $${a.price_usd.toFixed(4)} - ${expandedValidator}`
        : `${a.type === 'deposit' ? 'Stake' : 'Unstake'} - ${a.wallet || ''}`;
      
      return [
        `${a.date} ${time}:00 UTC`,
        isIncoming ? '' : a.amount_near.toFixed(8),
        isIncoming ? '' : 'NEAR',
        isIncoming ? a.amount_near.toFixed(8) : '',
        isIncoming ? 'NEAR' : '',
        '',
        '',
        a.value_usd.toFixed(2),
        'USD',
        label,
        desc,
        a.tx_hash || `epoch-${a.date}-${time}`
      ];
    });
    
    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `staking-${expandedValidator?.replace('.pool.near', '')}-${dateFilter}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const addValidator = async () => {
    if (!newPoolId.trim()) return;
    setAdding(true);
    try {
      const res = await fetch('/api/validators', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ poolId: newPoolId.trim(), isOwner: isOwnerNew }),
      });
      if (res.ok) {
        setNewPoolId('');
        setIsOwnerNew(false);
        fetchValidators();
      }
    } catch {}
    setAdding(false);
  };

  const removeValidator = async (poolId: string) => {
    try {
      await fetch('/api/validators', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ poolId }),
      });
      fetchValidators();
    } catch {}
  };

  const filterLabels: Record<DateFilter, string> = {
    day: '24h', week: '7 Days', month: '30 Days', year: '1 Year', all: 'All Time', custom: 'Custom',
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="p-6 flex items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin" />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            Validator Tracking
          </CardTitle>
        </CardHeader>
        <CardContent>
          {totals && (
            <div className="bg-muted/50 p-4 rounded-lg mb-6">
              <p className="text-sm text-muted-foreground">Total Staked (Current Balance)</p>
              <p className="text-2xl font-bold">{formatNumber(totals.totalStaked)} Ⓝ</p>
            </div>
          )}

          {/* Add Validator */}
          <div className="flex gap-2 mb-6">
            <Input placeholder="pool.poolv1.near" value={newPoolId} onChange={(e) => setNewPoolId(e.target.value)} className="flex-1" />
            <label className="flex items-center gap-2 px-3 bg-muted rounded-md cursor-pointer">
              <input type="checkbox" checked={isOwnerNew} onChange={(e) => setIsOwnerNew(e.target.checked)} className="rounded" />
              <span className="text-sm"><Crown className="h-3 w-3 inline" /> Owner</span>
            </label>
            <Button onClick={addValidator} disabled={adding || !newPoolId.trim()}>
              {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Add
            </Button>
          </div>

          {/* Validators List */}
          <div className="space-y-4">
            {validators.length === 0 ? (
              <p className="text-muted-foreground text-center py-4">No validators tracked yet.</p>
            ) : (
              validators.map((v) => (
                <div key={v.poolId} className="border rounded-lg p-4">
                  <div className="flex justify-between items-start">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        {v.meta.logo && <img src={v.meta.logo} alt="" className="w-6 h-6 rounded-full" />}
                        <h3 className="font-semibold">
                          {v.meta.name || v.label || v.poolId}
                          {v.isOwner && <Badge variant="outline" className="ml-2 text-yellow-600 border-yellow-500"><Crown className="h-3 w-3 mr-1" /> Owner</Badge>}
                        </h3>
                        <a href={`https://nearblocks.io/address/${v.poolId}`} target="_blank" rel="noopener noreferrer" className="text-muted-foreground hover:text-primary">
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      </div>
                      <p className="text-sm text-muted-foreground">{v.poolId}</p>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mt-2 text-sm">
                        <div><span className="text-muted-foreground">Your Stake:</span> <span className="font-medium">{formatNumber(v.ownStake)} Ⓝ</span></div>
                        <div><span className="text-muted-foreground">Pool Total:</span> {formatNumber(v.totalStakedNear)} Ⓝ</div>
                        <div><span className="text-muted-foreground">Commission:</span> {v.commissionRate.toFixed(1)}%</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button variant="ghost" size="sm" onClick={() => toggleExpand(v.poolId)}>
                        {expandedValidator === v.poolId ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      </Button>
                      <Button variant="ghost" size="sm" className="text-red-500" onClick={() => removeValidator(v.poolId)}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>

                  {/* Expanded Detail View */}
                  {expandedValidator === v.poolId && (
                    <div className="mt-4 pt-4 border-t">
                      {detailLoading ? (
                        <div className="flex justify-center py-4"><Loader2 className="h-6 w-6 animate-spin" /></div>
                      ) : detailData ? (
                        <div className="space-y-4">
                          {/* All-Time Summary */}
                          {detailData.allTimeTotals && (
                            <div className="bg-green-500/10 rounded-lg p-4 border border-green-500/20">
                              <h4 className="font-semibold mb-3">All-Time Summary</h4>
                              <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
                                <div>
                                  <span className="text-muted-foreground">Deposited:</span>
                                  <p className="font-medium text-green-600">+{formatNumber(detailData.allTimeTotals.totalDeposits)} Ⓝ</p>
                                  <p className="text-xs text-muted-foreground">({detailData.allTimeTotals.depositCount} txns)</p>
                                </div>
                                <div>
                                  <span className="text-muted-foreground">Withdrawn:</span>
                                  <p className="font-medium text-red-500">-{formatNumber(detailData.allTimeTotals.totalWithdrawals)} Ⓝ</p>
                                  <p className="text-xs text-muted-foreground">({detailData.allTimeTotals.withdrawalCount} txns)</p>
                                </div>
                                <div>
                                  <span className="text-muted-foreground">Net Deposits:</span>
                                  <p className="font-medium">{formatNumber(detailData.allTimeTotals.netDeposits)} Ⓝ</p>
                                </div>
                                <div>
                                  <span className="text-muted-foreground">Rewards Earned:</span>
                                  <p className="font-medium text-green-600">+{formatNumber(detailData.allTimeTotals.accumulatedRewards)} Ⓝ</p>
                                  <p className="text-xs text-muted-foreground">(${formatNumber(detailData.allTimeTotals.accumulatedRewardsUsd)} • {detailData.allTimeTotals.epochCount} epochs)</p>
                                </div>
                                <div className="bg-green-500/20 rounded p-2">
                                  <span className="text-muted-foreground">Current Balance:</span>
                                  <p className="font-bold text-lg">{formatNumber(detailData.allTimeTotals.currentStake)} Ⓝ</p>
                                </div>
                              </div>
                              <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                                <Info className="h-3 w-3" />
                                <span>Rewards distributed across epochs proportionally by stake. Each epoch valued at historical NEAR price.</span>
                              </div>
                            </div>
                          )}

                          {/* Filters */}
                          <div className="flex flex-wrap items-center gap-2">
                            <Filter className="h-4 w-4 text-muted-foreground" />
                            <span className="text-sm text-muted-foreground">Period:</span>
                            {(['day', 'week', 'month', 'year', 'all'] as DateFilter[]).map((f) => (
                              <Button key={f} variant={dateFilter === f ? 'default' : 'outline'} size="sm" onClick={() => handleDateFilterChange(f)}>
                                {filterLabels[f]}
                              </Button>
                            ))}
                            <span className="text-muted-foreground mx-1">|</span>
                            <input type="date" value={customStartDate} onChange={(e) => setCustomStartDate(e.target.value)} className="bg-muted border border-input rounded px-2 py-1 text-sm h-9" />
                            <span className="text-muted-foreground text-sm">to</span>
                            <input type="date" value={customEndDate} onChange={(e) => setCustomEndDate(e.target.value)} className="bg-muted border border-input rounded px-2 py-1 text-sm h-9" />
                            <Button variant={dateFilter === 'custom' ? 'default' : 'outline'} size="sm" onClick={applyCustomDateFilter} disabled={!customStartDate || !customEndDate}>
                              Apply
                            </Button>
                          </div>

                          {/* Activity Type Filter + Export */}
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm text-muted-foreground">Show:</span>
                            {(['all', 'deposit', 'withdrawal', 'reward'] as ActivityFilter[]).map((f) => (
                              <Button key={f} variant={activityFilter === f ? 'default' : 'outline'} size="sm" onClick={() => setActivityFilter(f)}>
                                {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1) + 's'}
                              </Button>
                            ))}
                            <Button variant="outline" size="sm" onClick={exportToKoinlyCsv} disabled={!detailData?.stakingActivity?.length} className="ml-auto">
                              <Download className="h-4 w-4 mr-1" /> Export CSV
                            </Button>
                          </div>

                          {/* Period Summary */}
                          {detailData.periodTotals && (
                            <div className="bg-muted/30 rounded-lg p-3">
                              <h4 className="font-semibold text-sm mb-2">
                                {filterLabels[dateFilter]} Summary
                                {detailData.periodTotals.dateRange.from && (
                                  <span className="font-normal text-muted-foreground ml-2">
                                    ({detailData.periodTotals.dateRange.from} to {detailData.periodTotals.dateRange.to})
                                  </span>
                                )}
                              </h4>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                                <div><span className="text-muted-foreground">Deposits:</span> <span className="font-medium text-green-600">+{formatNumber(detailData.periodTotals.totalDeposits)} Ⓝ</span> <span className="text-xs text-muted-foreground">({detailData.periodTotals.depositCount})</span></div>
                                <div><span className="text-muted-foreground">Withdrawals:</span> <span className="font-medium text-red-500">-{formatNumber(detailData.periodTotals.totalWithdrawals)} Ⓝ</span> <span className="text-xs text-muted-foreground">({detailData.periodTotals.withdrawalCount})</span></div>
                                <div><span className="text-muted-foreground">Epoch Rewards:</span> <span className="font-medium text-green-600">+{formatNumber(detailData.periodTotals.totalRewards)} Ⓝ</span> <span className="text-xs text-muted-foreground">({detailData.periodTotals.epochCount} epochs)</span></div>
                                <div><span className="text-muted-foreground">Rewards Value:</span> <span className="font-medium">${formatNumber(detailData.periodTotals.totalRewardsUsd)}</span></div>
                              </div>
                            </div>
                          )}

                          {/* Staking Activity Table */}
                          {detailData.stakingActivity && detailData.stakingActivity.length > 0 ? (
                            <div className="overflow-x-auto border rounded max-h-[600px] overflow-y-auto">
                              <table className="w-full text-sm">
                                <thead className="sticky top-0 bg-background border-b">
                                  <tr>
                                    <th className="text-left py-2 px-2">Date</th>
                                    <th className="text-left py-2 px-2">Type</th>
                                    <th className="text-right py-2 px-2">Amount</th>
                                    <th className="text-right py-2 px-2">Price</th>
                                    <th className="text-right py-2 px-2">Value</th>
                                    <th className="text-right py-2 px-2">Cumulative</th>
                                    <th className="text-left py-2 px-2">Details</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {detailData.stakingActivity
                                    .filter(a => activityFilter === 'all' || a.type === activityFilter)
                                    .map((a, i) => (
                                      <tr key={i} className="border-b hover:bg-muted/50">
                                        <td className="py-2 px-2 whitespace-nowrap">
                                          {a.date}
                                          {a.epochTime && <span className="text-xs text-muted-foreground ml-1">{a.epochTime}</span>}
                                        </td>
                                        <td className="py-2 px-2">
                                          <Badge variant={a.type === 'deposit' ? 'default' : a.type === 'reward' ? 'secondary' : 'destructive'} className="text-xs">
                                            {a.type === 'reward' ? 'Epoch' : a.type === 'deposit' ? 'Deposit' : 'Withdraw'}
                                          </Badge>
                                        </td>
                                        <td className={`py-2 px-2 text-right font-medium ${a.type === 'withdrawal' ? 'text-red-500' : 'text-green-600'}`}>
                                          {a.type === 'withdrawal' ? '-' : '+'}{a.amount_near.toFixed(6)} Ⓝ
                                        </td>
                                        <td className="py-2 px-2 text-right text-muted-foreground">
                                          ${a.price_usd.toFixed(4)}
                                        </td>
                                        <td className="py-2 px-2 text-right">
                                          ${a.value_usd.toFixed(2)}
                                        </td>
                                        <td className="py-2 px-2 text-right font-medium">
                                          {formatNumber(a.cumulative_stake)} Ⓝ
                                        </td>
                                        <td className="py-2 px-2 text-xs text-muted-foreground">
                                          {a.tx_hash ? (
                                            <a href={`https://nearblocks.io/txns/${a.tx_hash}`} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">
                                              {a.tx_hash.substring(0, 8)}...
                                            </a>
                                          ) : a.wallet ? (
                                            <span>{a.wallet.length > 12 ? a.wallet.substring(0, 10) + '...' : a.wallet}</span>
                                          ) : (
                                            <span>Epoch reward</span>
                                          )}
                                        </td>
                                      </tr>
                                    ))}
                                </tbody>
                              </table>
                            </div>
                          ) : (
                            <p className="text-muted-foreground text-center py-4">No activity found for this period.</p>
                          )}
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

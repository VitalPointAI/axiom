'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { 
  TrendingUp, Plus, Trash2, ExternalLink, Loader2, 
  ChevronDown, ChevronUp, AlertCircle, Coins, Users,
  Calendar, Hash, Crown, Filter
} from 'lucide-react';
import { formatCurrency, formatNumber } from '@/lib/utils';

interface ValidatorMeta {
  name?: string;
  description?: string;
  url?: string;
  logo?: string;
  country?: string;
  country_code?: string;
}

interface StakeByWallet {
  account: string;
  staked: number;
}

interface ValidatorStats {
  poolId: string;
  label: string | null;
  isOwner: boolean;
  meta: ValidatorMeta;
  totalStakedNear: number;
  delegatorCount: number;
  ownStake: number;
  ownStakeByWallet: StakeByWallet[];
  othersStake: number;
  commissionRate: number;
  estimatedDailyRewards: number;
  estimatedMonthlyRewards: number;
  estimatedAnnualRewards: number;
  personalDailyRewards: number;
  personalMonthlyRewards: number;
  personalAnnualRewards: number;
  commissionDailyEarnings?: number;
  commissionMonthlyEarnings?: number;
  commissionAnnualEarnings?: number;
  isActive: boolean;
  lastUpdated: string;
}

interface EpochEarning {
  epoch_id: number;
  date: string;
  staked_balance_near: number;
  pool_total_stake_near: number;
  pool_reward_near: number;
  commission_rate: number;
  gross_reward_near: number;
  commission_near: number;
  reward_near: number;
  commission_earned_near?: number;
  commission_earned_usd?: number;
  price_usd: number;
  income_usd: number;
}

interface PeriodTotals {
  totalRewards: number;
  totalRewardsUsd: number;
  totalCommissionPaid: number;
  totalCommissionEarned: number;
  totalCommissionEarnedUsd: number;
  epochCount: number;
  dateRange: { from: string | null; to: string | null };
}

interface ValidatorResponse {
  validators: ValidatorStats[];
  totals: {
    totalStaked: number;
    dailyRewards: number;
    monthlyRewards: number;
    annualRewards: number;
    dailyCommissionEarnings?: number;
    monthlyCommissionEarnings?: number;
    annualCommissionEarnings?: number;
  };
  userWalletCount: number;
  apyInfo: {
    currentApy: number;
    note: string;
  };
}

interface ValidatorDetailResponse {
  validator: ValidatorStats;
  epochEarnings: EpochEarning[];
  periodTotals: PeriodTotals;
  currentEpoch: number;
  isOwner: boolean;
  apyInfo: {
    currentApy: number;
    epochsPerYear: number;
    note: string;
  };
}

type DateFilter = 'day' | 'week' | 'month' | 'year' | 'all' | 'custom';

export function ValidatorTracking() {
  const [validators, setValidators] = useState<ValidatorStats[]>([]);
  const [totals, setTotals] = useState<ValidatorResponse['totals'] | null>(null);
  const [apyInfo, setApyInfo] = useState<{ currentApy: number; note: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newPoolId, setNewPoolId] = useState('');
  const [isOwnerNew, setIsOwnerNew] = useState(false);
  const [adding, setAdding] = useState(false);
  const [expandedValidator, setExpandedValidator] = useState<string | null>(null);
  const [detailData, setDetailData] = useState<ValidatorDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [nearPrice, setNearPrice] = useState<number>(1.12);
  const [dateFilter, setDateFilter] = useState<DateFilter>('month');
  const [customStartDate, setCustomStartDate] = useState<string>('');
  const [customEndDate, setCustomEndDate] = useState<string>('');

  useEffect(() => {
    fetchValidators();
    fetchPrice();
  }, []);

  const fetchPrice = async () => {
    try {
      const res = await fetch('/api/price?symbol=NEAR');
      if (res.ok) {
        const data = await res.json();
        setNearPrice(data.price || 1.12);
      }
    } catch {}
  };

  const fetchValidators = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/validators');
      if (!res.ok) throw new Error('Failed to fetch');
      const data: ValidatorResponse = await res.json();
      setValidators(data.validators || []);
      setTotals(data.totals);
      setApyInfo(data.apyInfo);
    } catch (err) {
      setError('Failed to load validators');
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
      if (!res.ok) throw new Error('Failed to load validator details');
      const data: ValidatorDetailResponse = await res.json();
      setDetailData(data);
    } catch (err) {
      console.error('Error loading validator detail:', err);
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

  const handleDateFilterChange = async (filter: DateFilter, startDate?: string, endDate?: string) => {
    setDateFilter(filter);
    if (filter === 'custom') {
      if (startDate) setCustomStartDate(startDate);
      if (endDate) setCustomEndDate(endDate);
    }
    if (expandedValidator) {
      await fetchValidatorDetail(expandedValidator, filter, startDate || customStartDate, endDate || customEndDate);
    }
  };

  const applyCustomDateFilter = async () => {
    if (customStartDate && customEndDate && expandedValidator) {
      setDateFilter('custom');
      await fetchValidatorDetail(expandedValidator, 'custom', customStartDate, customEndDate);
    }
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
    day: '24h',
    week: '7 Days',
    month: '30 Days',
    year: '1 Year',
    all: 'All Time',
    custom: 'Custom',
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
      {/* Summary Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            Validator Tracking
            {apyInfo && (
              <Badge variant="secondary" className="ml-2">
                {apyInfo.currentApy.toFixed(1)}% APY
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {totals && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <div className="bg-muted/50 p-4 rounded-lg">
                <p className="text-sm text-muted-foreground">Total Staked</p>
                <p className="text-2xl font-bold">{formatNumber(totals.totalStaked)} Ⓝ</p>
                <p className="text-sm text-muted-foreground">${formatNumber(totals.totalStaked * nearPrice)}</p>
              </div>
              <div className="bg-muted/50 p-4 rounded-lg">
                <p className="text-sm text-muted-foreground">Daily Rewards</p>
                <p className="text-2xl font-bold text-green-600">+{totals.dailyRewards.toFixed(4)} Ⓝ</p>
                <p className="text-sm text-muted-foreground">${(totals.dailyRewards * nearPrice).toFixed(2)}/day</p>
              </div>
              <div className="bg-muted/50 p-4 rounded-lg">
                <p className="text-sm text-muted-foreground">Monthly Rewards</p>
                <p className="text-2xl font-bold text-green-600">+{totals.monthlyRewards.toFixed(2)} Ⓝ</p>
                <p className="text-sm text-muted-foreground">${(totals.monthlyRewards * nearPrice).toFixed(2)}/mo</p>
              </div>
              {totals.dailyCommissionEarnings && totals.dailyCommissionEarnings > 0 && (
                <div className="bg-yellow-500/10 p-4 rounded-lg border border-yellow-500/20">
                  <p className="text-sm text-yellow-600 flex items-center gap-1">
                    <Crown className="h-3 w-3" /> Commission Earnings
                  </p>
                  <p className="text-2xl font-bold text-yellow-600">+{totals.dailyCommissionEarnings.toFixed(4)} Ⓝ</p>
                  <p className="text-sm text-muted-foreground">${(totals.dailyCommissionEarnings * nearPrice).toFixed(2)}/day</p>
                </div>
              )}
            </div>
          )}

          {/* Add Validator */}
          <div className="flex gap-2 mb-6">
            <Input
              placeholder="pool.poolv1.near"
              value={newPoolId}
              onChange={(e) => setNewPoolId(e.target.value)}
              className="flex-1"
            />
            <label className="flex items-center gap-2 px-3 bg-muted rounded-md cursor-pointer">
              <input
                type="checkbox"
                checked={isOwnerNew}
                onChange={(e) => setIsOwnerNew(e.target.checked)}
                className="rounded"
              />
              <span className="text-sm flex items-center gap-1">
                <Crown className="h-3 w-3" /> I own this
              </span>
            </label>
            <Button onClick={addValidator} disabled={adding || !newPoolId.trim()}>
              {adding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Add
            </Button>
          </div>

          {/* Validators List */}
          <div className="space-y-3">
            {validators.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <Coins className="h-12 w-12 mx-auto mb-2 opacity-50" />
                <p>No validators tracked yet</p>
                <p className="text-sm">Add a validator pool ID above to start tracking</p>
              </div>
            ) : (
              validators.map((v) => (
                <div key={v.poolId} className="border rounded-lg p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold">{v.meta.name || v.poolId}</h3>
                        {v.isOwner && (
                          <Badge className="bg-yellow-500/20 text-yellow-600 border-yellow-500/30">
                            <Crown className="h-3 w-3 mr-1" /> Owner
                          </Badge>
                        )}
                        {v.isActive ? (
                          <Badge variant="secondary" className="bg-green-500/20 text-green-600">Active</Badge>
                        ) : (
                          <Badge variant="secondary" className="bg-red-500/20 text-red-600">Inactive</Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground font-mono">{v.poolId}</p>
                      
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-3 text-sm">
                        <div>
                          <span className="text-muted-foreground">Your Stake:</span>
                          <span className="ml-1 font-medium">{formatNumber(v.ownStake)} Ⓝ</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Total Pool:</span>
                          <span className="ml-1">{formatNumber(v.totalStakedNear)} Ⓝ</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Commission:</span>
                          <span className="ml-1">{v.commissionRate.toFixed(1)}%</span>
                        </div>
                        <div>
                          <span className="text-muted-foreground">Daily Reward:</span>
                          <span className="ml-1 text-green-600">+{v.personalDailyRewards.toFixed(4)} Ⓝ</span>
                        </div>
                        {v.isOwner && v.commissionDailyEarnings && (
                          <div className="col-span-2">
                            <span className="text-yellow-600">Commission Earned:</span>
                            <span className="ml-1 text-yellow-600 font-medium">
                              +{v.commissionDailyEarnings.toFixed(4)} Ⓝ/day 
                              (${(v.commissionDailyEarnings * nearPrice).toFixed(2)})
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => toggleExpand(v.poolId)}
                      >
                        {expandedValidator === v.poolId ? (
                          <ChevronUp className="h-4 w-4" />
                        ) : (
                          <ChevronDown className="h-4 w-4" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-red-500"
                        onClick={() => removeValidator(v.poolId)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>

                  {/* Expanded Detail View */}
                  {expandedValidator === v.poolId && (
                    <div className="mt-4 pt-4 border-t">
                      {detailLoading ? (
                        <div className="flex justify-center py-4">
                          <Loader2 className="h-6 w-6 animate-spin" />
                        </div>
                      ) : detailData ? (
                        <div className="space-y-4">
                          {/* Date Filter */}
                          <div className="flex flex-wrap items-center gap-2">
                            <Filter className="h-4 w-4 text-muted-foreground" />
                            <span className="text-sm text-muted-foreground">Period:</span>
                            {(['day', 'week', 'month', 'year', 'all'] as DateFilter[]).map((f) => (
                              <Button
                                key={f}
                                variant={dateFilter === f ? 'default' : 'outline'}
                                size="sm"
                                onClick={() => handleDateFilterChange(f)}
                              >
                                {filterLabels[f]}
                              </Button>
                            ))}
                            <span className="text-muted-foreground mx-1">|</span>
                            <input
                              type="date"
                              value={customStartDate}
                              onChange={(e) => setCustomStartDate(e.target.value)}
                              className="bg-muted border border-input rounded px-2 py-1 text-sm h-9"
                            />
                            <span className="text-muted-foreground text-sm">to</span>
                            <input
                              type="date"
                              value={customEndDate}
                              onChange={(e) => setCustomEndDate(e.target.value)}
                              className="bg-muted border border-input rounded px-2 py-1 text-sm h-9"
                            />
                            <Button
                              variant={dateFilter === 'custom' ? 'default' : 'outline'}
                              size="sm"
                              onClick={applyCustomDateFilter}
                              disabled={!customStartDate || !customEndDate}
                            >
                              Apply
                            </Button>
                          </div>

                          {/* Period Summary */}
                          {detailData.periodTotals && (
                            <div className="bg-muted/30 rounded-lg p-4">
                              <h4 className="font-semibold mb-2">
                                {filterLabels[dateFilter]} Summary
                                {detailData.periodTotals.dateRange.from && (
                                  <span className="font-normal text-sm text-muted-foreground ml-2">
                                    ({detailData.periodTotals.dateRange.from} to {detailData.periodTotals.dateRange.to})
                                  </span>
                                )}
                              </h4>
                              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                                <div>
                                  <span className="text-muted-foreground">Epochs:</span>
                                  <span className="ml-1 font-medium">{detailData.periodTotals.epochCount}</span>
                                </div>
                                <div>
                                  <span className="text-muted-foreground">Net Rewards:</span>
                                  <span className="ml-1 font-medium text-green-600">
                                    +{detailData.periodTotals.totalRewards.toFixed(4)} Ⓝ
                                  </span>
                                </div>
                                <div>
                                  <span className="text-muted-foreground">Commission Paid:</span>
                                  <span className="ml-1 text-red-500">
                                    -{detailData.periodTotals.totalCommissionPaid.toFixed(4)} Ⓝ
                                  </span>
                                </div>
                                <div>
                                  <span className="text-muted-foreground">Value (USD):</span>
                                  <span className="ml-1 font-medium">
                                    ${detailData.periodTotals.totalRewardsUsd.toFixed(2)}
                                  </span>
                                </div>
                                {detailData.isOwner && detailData.periodTotals.totalCommissionEarned > 0 && (
                                  <>
                                    <div className="col-span-2 bg-yellow-500/10 p-2 rounded border border-yellow-500/20">
                                      <span className="text-yellow-600 flex items-center gap-1">
                                        <Crown className="h-3 w-3" /> Commission Earned:
                                      </span>
                                      <span className="ml-1 font-bold text-yellow-600">
                                        +{detailData.periodTotals.totalCommissionEarned.toFixed(4)} Ⓝ
                                        (${detailData.periodTotals.totalCommissionEarnedUsd.toFixed(2)})
                                      </span>
                                    </div>
                                  </>
                                )}
                              </div>
                            </div>
                          )}

                          {/* Epoch Earnings History <span className="text-xs text-muted-foreground font-normal">(Estimated based on current stake)</span> */}
                          <div>
                            <h4 className="font-semibold mb-2 flex items-center gap-2">
                              <Calendar className="h-4 w-4" />
                              Epoch Earnings History <span className="text-xs text-muted-foreground font-normal">(Estimated based on current stake)</span>
                            </h4>
                            <div className="overflow-x-auto">
                              <table className="w-full text-sm">
                                <thead>
                                  <tr className="border-b">
                                    <th className="text-left py-2 px-2">Epoch</th>
                                    <th className="text-left py-2 px-2">Date</th>
                                    <th className="text-right py-2 px-2">Your Stake</th>
                                    <th className="text-right py-2 px-2">Gross Reward</th>
                                    <th className="text-right py-2 px-2">Commission Paid</th>
                                    <th className="text-right py-2 px-2">Net Reward</th>
                                    {detailData.isOwner && (
                                      <th className="text-right py-2 px-2 bg-yellow-500/10">
                                        <span className="flex items-center justify-end gap-1">
                                          <Crown className="h-3 w-3" /> Earned
                                        </span>
                                      </th>
                                    )}
                                    <th className="text-right py-2 px-2">Value (USD)</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {detailData.epochEarnings.slice(0, 50).map((e, i) => (
                                    <tr key={i} className="border-b hover:bg-muted/50">
                                      <td className="py-2 px-2 font-mono text-xs">#{e.epoch_id}</td>
                                      <td className="py-2 px-2">{e.date}</td>
                                      <td className="py-2 px-2 text-right">
                                        {formatNumber(e.staked_balance_near)}
                                      </td>
                                      <td className="py-2 px-2 text-right text-muted-foreground">
                                        {e.gross_reward_near.toFixed(6)}
                                      </td>
                                      <td className="py-2 px-2 text-right text-red-500">
                                        -{e.commission_near.toFixed(6)}
                                      </td>
                                      <td className="py-2 px-2 text-right text-green-600 font-medium">
                                        +{e.reward_near.toFixed(6)}
                                      </td>
                                      {detailData.isOwner && (
                                        <td className="py-2 px-2 text-right text-yellow-600 font-medium bg-yellow-500/5">
                                          +{(e.commission_earned_near || 0).toFixed(6)}
                                        </td>
                                      )}
                                      <td className="py-2 px-2 text-right">
                                        ${e.income_usd?.toFixed(4) || '-'}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                            {detailData.epochEarnings.length > 50 && (
                              <p className="text-xs text-muted-foreground mt-2">
                                Showing 50 of {detailData.epochEarnings.length} epochs
                              </p>
                            )}
                          </div>
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

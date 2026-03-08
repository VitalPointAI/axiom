import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { getAuthenticatedUser } from "@/lib/auth";

const NEAR_RPC = 'https://rpc.fastnear.com';
const STAKING_APY = 0.045;
const EPOCHS_PER_YEAR = 730;

async function rpcCall(method: string, params: any): Promise<any> {
  try {
    const res = await fetch(NEAR_RPC, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', id: '1', method, params }),
    });
    return await res.json();
  } catch {
    return { error: 'RPC error' };
  }
}

interface ValidatorMeta {
  name?: string;
  description?: string;
  url?: string;
  logo?: string;
  country?: string;
  country_code?: string;
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
  othersStake: number;
  commissionRate: number;
  estimatedDailyRewards: number;
  estimatedMonthlyRewards: number;
  estimatedAnnualRewards: number;
  personalDailyRewards: number;
  personalMonthlyRewards: number;
  personalAnnualRewards: number;
  // For owners: commission earnings
  commissionDailyEarnings?: number;
  commissionMonthlyEarnings?: number;
  commissionAnnualEarnings?: number;
  isActive: boolean;
  lastUpdated: string;
}

async function getValidatorMeta(poolId: string): Promise<ValidatorMeta> {
  try {
    const poolArgs = Buffer.from('{}').toString('base64');
    const fieldsData = await rpcCall('query', {
      request_type: 'call_function',
      finality: 'final',
      account_id: poolId,
      method_name: 'get_fields',
      args_base64: poolArgs
    });
    
    if (fieldsData.result?.result) {
      try {
        const decoded = Buffer.from(fieldsData.result.result).toString();
        const fields = JSON.parse(decoded);
        return {
          name: fields.name,
          description: fields.description,
          url: fields.url,
          logo: fields.logo || fields.icon,
          country: fields.country,
          country_code: fields.country_code,
        };
      } catch {}
    }
    return {};
  } catch {
    return {};
  }
}

async function getAccountStake(poolId: string, accountId: string): Promise<number> {
  try {
    const args = Buffer.from(JSON.stringify({ account_id: accountId })).toString('base64');
    const result = await rpcCall('query', {
      request_type: 'call_function',
      finality: 'final',
      account_id: poolId,
      method_name: 'get_account_staked_balance',
      args_base64: args
    });
    if (result.result?.result) {
      const balance = Buffer.from(result.result.result).toString().replace(/"/g, '');
      return parseFloat(balance) / 1e24;
    }
    return 0;
  } catch {
    return 0;
  }
}

async function getCurrentEpoch(): Promise<number> {
  try {
    const result = await rpcCall('validators', [null]);
    return result.result?.epoch_height || 0;
  } catch {
    return 0;
  }
}

async function getValidatorStats(poolId: string, userWallets: string[], isOwner: boolean): Promise<ValidatorStats | null> {
  try {
    // Get total staked
    const totalArgs = Buffer.from('{}').toString('base64');
    const totalResult = await rpcCall('query', {
      request_type: 'call_function',
      finality: 'final',
      account_id: poolId,
      method_name: 'get_total_staked_balance',
      args_base64: totalArgs
    });
    
    // Get number of accounts
    const countResult = await rpcCall('query', {
      request_type: 'call_function',
      finality: 'final',
      account_id: poolId,
      method_name: 'get_number_of_accounts',
      args_base64: totalArgs
    });
    
    // Get reward fee fraction (commission)
    const feeResult = await rpcCall('query', {
      request_type: 'call_function',
      finality: 'final',
      account_id: poolId,
      method_name: 'get_reward_fee_fraction',
      args_base64: totalArgs
    });

    const totalStaked = totalResult.result?.result 
      ? parseFloat(Buffer.from(totalResult.result.result).toString().replace(/"/g, '')) / 1e24 
      : 0;
    
    const delegatorCount = countResult.result?.result
      ? parseInt(Buffer.from(countResult.result.result).toString())
      : 0;

    let commissionRate = 0;
    if (feeResult.result?.result) {
      try {
        const feeData = JSON.parse(Buffer.from(feeResult.result.result).toString());
        commissionRate = (feeData.numerator / feeData.denominator) * 100;
      } catch {}
    }

    // Get user's stake in this pool from ALL wallets
    const ownStakeByWallet: { account: string; staked: number }[] = [];
    let ownStake = 0;
    for (const wallet of userWallets) {
      const stake = await getAccountStake(poolId, wallet);
      if (stake > 0) {
        ownStakeByWallet.push({ account: wallet, staked: stake });
        ownStake += stake;
      }
    }

    const othersStake = totalStaked - ownStake;
    const meta = await getValidatorMeta(poolId);
    
    // Calculate rewards
    const epochRate = STAKING_APY / EPOCHS_PER_YEAR;
    const poolDailyReward = totalStaked * epochRate * 2; // 2 epochs per day
    const userShare = ownStake / totalStaked;
    const grossDailyReward = poolDailyReward * userShare;
    const commissionPaid = grossDailyReward * (commissionRate / 100);
    const netDailyReward = grossDailyReward - commissionPaid;
    
    // For owners: commission EARNED from others' stakes
    const othersShare = othersStake / totalStaked;
    const othersGrossReward = poolDailyReward * othersShare;
    const commissionEarned = othersGrossReward * (commissionRate / 100);

    const stats: ValidatorStats = {
      poolId,
      label: null,
      isOwner,
      meta,
      totalStakedNear: totalStaked,
      delegatorCount,
      ownStake,
      ownStakeByWallet,
      othersStake,
      commissionRate,
      estimatedDailyRewards: poolDailyReward,
      estimatedMonthlyRewards: poolDailyReward * 30,
      estimatedAnnualRewards: poolDailyReward * 365,
      personalDailyRewards: netDailyReward,
      personalMonthlyRewards: netDailyReward * 30,
      personalAnnualRewards: netDailyReward * 365,
      isActive: totalStaked > 0,
      lastUpdated: new Date().toISOString(),
    };
    
    // Add commission earnings for owners
    if (isOwner) {
      stats.commissionDailyEarnings = commissionEarned;
      stats.commissionMonthlyEarnings = commissionEarned * 30;
      stats.commissionAnnualEarnings = commissionEarned * 365;
    }

    return stats;
  } catch (error) {
    console.error(`Error getting validator stats for ${poolId}:`, error);
    return null;
  }
}

export async function GET(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();
    const userWallets = await db.prepare(`SELECT account_id FROM wallets WHERE user_id = ?`).all(auth.userId) as { account_id: string }[];
    const walletAccounts = userWallets.map(w => w.account_id);
    
    const poolIdParam = request.nextUrl.searchParams.get('poolId');
    const dateFilter = request.nextUrl.searchParams.get('dateFilter'); // day, week, month, year
    const customStartDate = request.nextUrl.searchParams.get('startDate');
    const customEndDate = request.nextUrl.searchParams.get('endDate');

    // Single validator detail view
    if (poolIdParam) {
      const validator = await db.prepare(`
        SELECT pool_id, label, is_owner FROM user_validators 
        WHERE user_id = ? AND pool_id = ?
      `).get(auth.userId, poolIdParam) as { pool_id: string; label: string | null; is_owner: number } | undefined;

      if (!validator) {
        return NextResponse.json({ error: 'Validator not found' }, { status: 404 });
      }

      const isOwner = validator.is_owner === 1;
      const stats = await getValidatorStats(validator.pool_id, walletAccounts, isOwner);
      if (stats) {
        stats.label = validator.label;
        stats.isOwner = isOwner;
      }

      const currentEpoch = await getCurrentEpoch();

      // Get epoch rewards from DB or generate
      let epochEarnings = await db.prepare(`
        SELECT 
          epoch_id, epoch_date as date, staked_balance_near,
          pool_total_stake_near, pool_reward_near, commission_rate,
          gross_reward_near, commission_near, net_reward_near as reward_near,
          price_usd, net_reward_usd as income_usd
        FROM epoch_rewards
        WHERE validator = ?
        ORDER BY epoch_id DESC
        LIMIT 200
      `).all(poolIdParam) as any[];

      // Generate estimated data if no DB data
      if (epochEarnings.length === 0 && stats) {
        const epochRate = STAKING_APY / EPOCHS_PER_YEAR;
        epochEarnings = [];
        for (let i = 0; i < 200; i++) {
          const epochId = currentEpoch - i;
          const epochTime = Date.now() - (i * 12 * 3600 * 1000);
          const date = new Date(epochTime).toISOString().split('T')[0];
          
          const poolReward = stats.totalStakedNear * epochRate;
          const userShare = stats.ownStake / stats.totalStakedNear;
          const grossReward = poolReward * userShare;
          const commission = grossReward * (stats.commissionRate / 100);
          const netReward = grossReward - commission;
          
          // For owners: calculate commission EARNED
          const othersShare = stats.othersStake / stats.totalStakedNear;
          const othersGross = poolReward * othersShare;
          const commissionEarned = othersGross * (stats.commissionRate / 100);
          
          // Add slight variance to simulate real-world fluctuations in stake/rewards
          // (Until we implement proper historical epoch tracking)
          const variance = 1 + (Math.sin(epochId * 0.1) * 0.03); // +/- 3% variance
          const adjustedOwnStake = stats.ownStake * variance;
          const adjustedPoolReward = poolReward * variance;
          const adjustedGrossReward = grossReward * variance;
          const adjustedCommission = commission * variance;
          const adjustedNetReward = netReward * variance;
          const adjustedCommissionEarned = commissionEarned * variance;
          
          // Historical price estimation (rough - ideally fetch from price API)
          const daysAgo = i * 0.5; // 2 epochs per day
          const priceVariance = 1 + (Math.sin(epochId * 0.2) * 0.1); // +/- 10% price variance
          const basePrice = 1.15;
          const historicalPrice = basePrice * priceVariance;
          
          epochEarnings.push({
            epoch_id: epochId,
            date,
            staked_balance_near: adjustedOwnStake,
            pool_total_stake_near: stats.totalStakedNear * variance,
            pool_reward_near: adjustedPoolReward,
            commission_rate: stats.commissionRate,
            gross_reward_near: adjustedGrossReward,
            commission_near: adjustedCommission,
            reward_near: adjustedNetReward,
            commission_earned_near: isOwner ? adjustedCommissionEarned : 0,
            price_usd: historicalPrice,
            income_usd: adjustedNetReward * historicalPrice,
            commission_earned_usd: isOwner ? adjustedCommissionEarned * historicalPrice : 0,
            is_estimated: true,
          });
        }
      } else if (isOwner && epochEarnings.length > 0 && stats) {
        // Add commission_earned to existing data for owners
        epochEarnings = epochEarnings.map(e => {
          const othersStake = e.pool_total_stake_near - e.staked_balance_near;
          const othersShare = othersStake / e.pool_total_stake_near;
          const othersGross = e.pool_reward_near * othersShare;
          const commissionEarned = othersGross * (e.commission_rate / 100);
          return {
            ...e,
            commission_earned_near: commissionEarned,
            commission_earned_usd: commissionEarned * (e.price_usd || 1.12),
          };
        });
      }

      // Apply date filter for summary
      let filteredEarnings = epochEarnings;
      const now = new Date();
      // Apply date filter
      if (customStartDate && customEndDate) {
        const startDate = new Date(customStartDate);
        const endDate = new Date(customEndDate);
        endDate.setHours(23, 59, 59, 999);
        filteredEarnings = epochEarnings.filter(e => {
          const d = new Date(e.date);
          return d >= startDate && d <= endDate;
        });
      } else if (dateFilter) {
        let cutoffDate: Date;
        switch (dateFilter) {
          case 'day':
            cutoffDate = new Date(now.getTime() - 24 * 60 * 60 * 1000);
            break;
          case 'week':
            cutoffDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            break;
          case 'month':
            cutoffDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            break;
          case 'year':
            cutoffDate = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000);
            break;
          default:
            cutoffDate = new Date(0);
        }
        filteredEarnings = epochEarnings.filter(e => new Date(e.date) >= cutoffDate);
      }

      // Calculate period totals
      const periodTotals = {
        totalRewards: filteredEarnings.reduce((sum, e) => sum + (e.reward_near || 0), 0),
        totalRewardsUsd: filteredEarnings.reduce((sum, e) => sum + (e.income_usd || 0), 0),
        totalCommissionPaid: filteredEarnings.reduce((sum, e) => sum + (e.commission_near || 0), 0),
        totalCommissionEarned: filteredEarnings.reduce((sum, e) => sum + (e.commission_earned_near || 0), 0),
        totalCommissionEarnedUsd: filteredEarnings.reduce((sum, e) => sum + (e.commission_earned_usd || 0), 0),
        epochCount: filteredEarnings.length,
        dateRange: {
          from: filteredEarnings.length > 0 ? filteredEarnings[filteredEarnings.length - 1].date : null,
          to: filteredEarnings.length > 0 ? filteredEarnings[0].date : null,
        }
      };

      return NextResponse.json({
        validator: stats,
        epochEarnings: filteredEarnings.slice(0, 100),
        periodTotals,
        currentEpoch,
        isOwner,
        apyInfo: {
          currentApy: STAKING_APY * 100,
          epochsPerYear: EPOCHS_PER_YEAR,
          note: 'NEAR staking APY was halved in early 2026',
        },
      });
    }

    // List all validators
    const userValidators = await db.prepare(`
      SELECT pool_id, label, is_owner FROM user_validators WHERE user_id = ?
    `).all(auth.userId) as { pool_id: string; label: string | null; is_owner: number }[];

    const validators: ValidatorStats[] = [];
    let totalStaked = 0;
    let totalDailyRewards = 0;
    let totalCommissionEarnings = 0;

    for (const v of userValidators) {
      const isOwner = v.is_owner === 1;
      const stats = await getValidatorStats(v.pool_id, walletAccounts, isOwner);
      if (stats) {
        stats.label = v.label;
        stats.isOwner = isOwner;
        validators.push(stats);
        totalStaked += stats.ownStake;
        totalDailyRewards += stats.personalDailyRewards;
        if (isOwner && stats.commissionDailyEarnings) {
          totalCommissionEarnings += stats.commissionDailyEarnings;
        }
      }
    }

    return NextResponse.json({
      validators,
      totals: {
        totalStaked,
        dailyRewards: totalDailyRewards,
        monthlyRewards: totalDailyRewards * 30,
        annualRewards: totalDailyRewards * 365,
        dailyCommissionEarnings: totalCommissionEarnings,
        monthlyCommissionEarnings: totalCommissionEarnings * 30,
        annualCommissionEarnings: totalCommissionEarnings * 365,
      },
      userWalletCount: walletAccounts.length,
      apyInfo: {
        currentApy: STAKING_APY * 100,
        note: 'NEAR staking APY was halved in early 2026',
      },
    });
  } catch (error) {
    console.error('Validators API error:', error);
    return NextResponse.json({ error: 'Failed to fetch validators' }, { status: 500 });
  }
}

// POST to add/update validator
export async function POST(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { poolId, label, isOwner } = await request.json();
    if (!poolId) {
      return NextResponse.json({ error: 'Pool ID required' }, { status: 400 });
    }

    const db = getDb();
    await db.prepare(`
      INSERT INTO user_validators (user_id, pool_id, label, is_owner, added_at)
      VALUES (?, ?, ?, ?, datetime('now'))
      ON CONFLICT(user_id, pool_id) DO UPDATE SET label = ?, is_owner = ?
    `).run(auth.userId, poolId, label || null, isOwner ? 1 : 0, label || null, isOwner ? 1 : 0);

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Add validator error:', error);
    return NextResponse.json({ error: 'Failed to add validator' }, { status: 500 });
  }
}

// DELETE validator
export async function DELETE(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { poolId } = await request.json();
    if (!poolId) {
      return NextResponse.json({ error: 'Pool ID required' }, { status: 400 });
    }

    const db = getDb();
    await db.prepare('DELETE FROM user_validators WHERE user_id = ? AND pool_id = ?').run(auth.userId, poolId);

    return NextResponse.json({ success: true });
  } catch (error) {
    return NextResponse.json({ error: 'Failed to delete validator' }, { status: 500 });
  }
}

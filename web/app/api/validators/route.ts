import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { getAuthenticatedUser } from "@/lib/auth";

const NEAR_RPC = 'https://rpc.fastnear.com';
const EPOCHS_PER_DAY = 2;

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

async function getValidatorStats(poolId: string, userWallets: string[], isOwner: boolean): Promise<ValidatorStats | null> {
  try {
    const totalArgs = Buffer.from('{}').toString('base64');
    const totalResult = await rpcCall('query', {
      request_type: 'call_function',
      finality: 'final',
      account_id: poolId,
      method_name: 'get_total_staked_balance',
      args_base64: totalArgs
    });
    
    const countResult = await rpcCall('query', {
      request_type: 'call_function',
      finality: 'final',
      account_id: poolId,
      method_name: 'get_number_of_accounts',
      args_base64: totalArgs
    });
    
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

    const ownStakeByWallet: { account: string; staked: number }[] = [];
    let ownStake = 0;
    for (const wallet of userWallets) {
      const stake = await getAccountStake(poolId, wallet);
      if (stake > 0) {
        ownStakeByWallet.push({ account: wallet, staked: stake });
        ownStake += stake;
      }
    }

    const meta = await getValidatorMeta(poolId);

    return {
      poolId,
      label: null,
      isOwner,
      meta,
      totalStakedNear: totalStaked,
      delegatorCount,
      ownStake,
      ownStakeByWallet,
      commissionRate,
      isActive: totalStaked > 0,
      lastUpdated: new Date().toISOString(),
    };
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
    const dateFilter = request.nextUrl.searchParams.get('dateFilter');
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

      const currentStake = stats?.ownStake || 0;

      // Get ALL staking events sorted by timestamp ASC
      const allStakingEvents = await db.prepare(`
        SELECT 
          se.id,
          se.event_type,
          CAST(se.amount AS NUMERIC) / 1e24 as amount_near,
          se.block_timestamp,
          se.tx_hash,
          w.account_id as wallet,
          TO_CHAR(TO_TIMESTAMP(se.block_timestamp::bigint / 1000000000), 'YYYY-MM-DD') as date
        FROM staking_events se
        JOIN wallets w ON se.wallet_id = w.id
        WHERE se.validator_id = $1 AND w.account_id = ANY($2::text[])
        ORDER BY se.block_timestamp ASC
      `).all(poolIdParam, walletAccounts) as any[];

      if (allStakingEvents.length === 0) {
        return NextResponse.json({
          validator: stats,
          stakingActivity: [],
          periodTotals: { totalDeposits: 0, totalWithdrawals: 0, totalRewards: 0, totalRewardsUsd: 0, depositCount: 0, withdrawalCount: 0, epochCount: 0, dateRange: { from: null, to: null } },
          allTimeTotals: { totalDeposits: 0, totalWithdrawals: 0, netDeposits: 0, currentStake, accumulatedRewards: 0, depositCount: 0, withdrawalCount: 0, epochCount: 0 },
          isOwner,
        });
      }

      // Calculate totals from real transactions
      const totalDeposits = allStakingEvents.filter(e => e.event_type === 'stake').reduce((sum, e) => sum + (Number(e.amount_near) || 0), 0);
      const totalWithdrawals = allStakingEvents.filter(e => e.event_type === 'unstake').reduce((sum, e) => sum + (Number(e.amount_near) || 0), 0);
      const netDeposits = totalDeposits - totalWithdrawals;
      
      // REAL total rewards = current balance - net deposits
      const totalRewards = Math.max(0, currentStake - netDeposits);

      // Get date range
      const firstDate = new Date(allStakingEvents[0].date);
      const today = new Date();
      today.setHours(23, 59, 59, 999);

      // Fetch ALL historical NEAR prices
      const priceRows = await db.prepare(`
        SELECT date, price FROM price_cache 
        WHERE coin_id = 'NEAR' AND currency = 'USD'
        ORDER BY date
      `).all() as { date: string; price: number }[];
      
      // Build price lookup map (date -> price)
      const priceByDate: Map<string, number> = new Map();
      for (const row of priceRows) {
        const dateOnly = row.date.split(' ')[0]; // Extract YYYY-MM-DD from 'YYYY-MM-DD HH:MM'
        priceByDate.set(dateOnly, row.price);
      }
      
      // Get current price as fallback
      let currentPrice = 1.12;
      try {
        const priceRes = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=near&vs_currencies=usd');
        if (priceRes.ok) {
          const priceData = await priceRes.json();
          currentPrice = priceData.near?.usd || 1.12;
        }
      } catch {}

      // Build stake-by-date map
      const stakeChanges: { date: string; timestamp: number; stake: number; event: any }[] = [];
      let runningStake = 0;
      
      for (const e of allStakingEvents) {
        const amount = Number(e.amount_near) || 0;
        if (e.event_type === 'stake') {
          runningStake += amount;
        } else {
          runningStake -= amount;
        }
        stakeChanges.push({
          date: e.date,
          timestamp: Number(e.block_timestamp),
          stake: runningStake,
          event: e,
        });
      }

      // Build daily stakes and calculate total stake-epochs for reward distribution
      const dailyStakes: { date: string; stake: number }[] = [];
      let currentDate = new Date(firstDate);
      let lastKnownStake = 0;
      let totalStakeEpochs = 0;
      
      while (currentDate <= today) {
        const dateStr = currentDate.toISOString().split('T')[0];
        
        const changesOnDate = stakeChanges.filter(sc => sc.date === dateStr);
        if (changesOnDate.length > 0) {
          lastKnownStake = changesOnDate[changesOnDate.length - 1].stake;
        }
        
        if (lastKnownStake > 0) {
          dailyStakes.push({ date: dateStr, stake: lastKnownStake });
          totalStakeEpochs += lastKnownStake * EPOCHS_PER_DAY; // 2 epochs per day
        }
        
        currentDate.setDate(currentDate.getDate() + 1);
      }

      // Calculate REAL per-epoch rewards from balance snapshots
      const epochRewards: any[] = [];
      
      // Fetch balance snapshots for this validator/wallet combination
      const snapshots = await db.prepare(`
        SELECT 
          sbs.epoch_id,
          sbs.epoch_timestamp,
          CAST(sbs.staked_balance AS NUMERIC) / 1e24 as staked_near,
          CAST(sbs.unstaked_balance AS NUMERIC) / 1e24 as unstaked_near,
          TO_CHAR(TO_TIMESTAMP(sbs.epoch_timestamp::bigint / 1000000000), 'YYYY-MM-DD') as date
        FROM staking_balance_snapshots sbs
        JOIN wallets w ON sbs.wallet_id = w.id
        WHERE sbs.validator_id = $1 
          AND w.account_id = ANY($2::text[])
        ORDER BY sbs.epoch_id ASC
      `).all(poolIdParam, walletAccounts) as any[];
      
      if (snapshots.length >= 2) {
        // Calculate rewards between consecutive snapshots
        for (let i = 1; i < snapshots.length; i++) {
          const prev = snapshots[i - 1];
          const curr = snapshots[i];
          
          // Get deposits/withdrawals between these epochs
          const epochStart = prev.epoch_timestamp;
          const epochEnd = curr.epoch_timestamp;
          
          const depositsInPeriod = allStakingEvents
            .filter(e => e.event_type === 'stake' && 
                        Number(e.block_timestamp) > epochStart && 
                        Number(e.block_timestamp) <= epochEnd)
            .reduce((sum, e) => sum + (Number(e.amount_near) || 0), 0);
          
          const withdrawalsInPeriod = allStakingEvents
            .filter(e => e.event_type === 'unstake' && 
                        Number(e.block_timestamp) > epochStart && 
                        Number(e.block_timestamp) <= epochEnd)
            .reduce((sum, e) => sum + (Number(e.amount_near) || 0), 0);
          
          // Real reward = balance change - deposits + withdrawals
          const balanceChange = curr.staked_near - prev.staked_near;
          const realReward = balanceChange - depositsInPeriod + withdrawalsInPeriod;
          
          // Only include positive rewards (negative could be slashing or rounding)
          if (realReward > 0.0001) {
            const epochPrice = priceByDate.get(curr.date) || currentPrice;
            epochRewards.push({
              date: curr.date,
              epochNum: curr.epoch_id,
              epochTime: 'Epoch ' + curr.epoch_id,
              reward_near: realReward,
              price_usd: epochPrice,
              value_usd: realReward * epochPrice,
              stakeAtEpoch: curr.staked_near,
              note: 'Real reward from balance snapshot'
            });
          }
        }
      }
      
      // If no snapshots yet, show total accumulated rewards as single entry
      if (epochRewards.length === 0 && totalRewards > 0) {
        const latestPrice = priceByDate.get(dailyStakes[dailyStakes.length - 1]?.date) || currentPrice;
        epochRewards.push({
          date: dailyStakes.length > 0 ? dailyStakes[dailyStakes.length - 1].date : new Date().toISOString().split('T')[0],
          epochNum: 0,
          epochTime: 'Total',
          reward_near: totalRewards,
          price_usd: latestPrice,
          value_usd: totalRewards * latestPrice,
          stakeAtEpoch: currentStake,
          note: 'Total accumulated (detailed tracking starts next epoch)'
        });
      }

      // Build unified activity list
      const allActivity: any[] = [];
      
      // Add deposit/withdrawal events
      for (const e of allStakingEvents) {
        const eventPrice = priceByDate.get(e.date) || currentPrice;
        allActivity.push({
          type: e.event_type === 'stake' ? 'deposit' : 'withdrawal',
          date: e.date,
          timestamp: Number(e.block_timestamp),
          amount_near: Number(e.amount_near),
          price_usd: eventPrice,
          value_usd: Number(e.amount_near) * eventPrice,
          wallet: e.wallet,
          tx_hash: e.tx_hash,
        });
      }
      
      // Add epoch reward entries
      for (const er of epochRewards) {
        const epochDate = new Date(er.date);
        const hours = er.epochTime === '00:00' ? 0 : 12;
        epochDate.setHours(hours, 0, 0, 0);
        
        allActivity.push({
          type: 'reward',
          date: er.date,
          epochTime: er.epochTime,
          timestamp: epochDate.getTime() * 1000000,
          amount_near: er.reward_near,
          price_usd: er.price_usd,
          value_usd: er.value_usd,
          stakeAtEpoch: er.stakeAtEpoch,
        });
      }
      
      // Sort chronologically
      allActivity.sort((a, b) => a.timestamp - b.timestamp);
      
      // Calculate cumulative stake (deposits + rewards - withdrawals)
      let cumulativeStake = 0;
      for (const activity of allActivity) {
        if (activity.type === 'deposit' || activity.type === 'reward') {
          cumulativeStake += activity.amount_near;
        } else if (activity.type === 'withdrawal') {
          cumulativeStake -= activity.amount_near;
        }
        activity.cumulative_stake = cumulativeStake;
      }

      // Apply date filter
      let filteredActivity = allActivity;
      const now = new Date();
      
      if (customStartDate && customEndDate) {
        const startDate = new Date(customStartDate);
        const endDateObj = new Date(customEndDate);
        endDateObj.setHours(23, 59, 59, 999);
        filteredActivity = allActivity.filter(e => {
          const d = new Date(e.date);
          return d >= startDate && d <= endDateObj;
        });
      } else if (dateFilter && dateFilter !== 'all') {
        let cutoffDate = new Date(0);
        switch (dateFilter) {
          case 'day': cutoffDate = new Date(now.getTime() - 24 * 60 * 60 * 1000); break;
          case 'week': cutoffDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000); break;
          case 'month': cutoffDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000); break;
          case 'year': cutoffDate = new Date(now.getTime() - 365 * 24 * 60 * 60 * 1000); break;
        }
        filteredActivity = allActivity.filter(e => new Date(e.date) >= cutoffDate);
      }

      // Sort newest first for display
      filteredActivity.sort((a, b) => b.timestamp - a.timestamp);

      // Period totals
      const rewardItems = filteredActivity.filter(e => e.type === 'reward');
      const periodTotals = {
        totalDeposits: filteredActivity.filter(e => e.type === 'deposit').reduce((sum, e) => sum + e.amount_near, 0),
        totalWithdrawals: filteredActivity.filter(e => e.type === 'withdrawal').reduce((sum, e) => sum + e.amount_near, 0),
        totalRewards: rewardItems.reduce((sum, e) => sum + e.amount_near, 0),
        totalRewardsUsd: rewardItems.reduce((sum, e) => sum + e.value_usd, 0),
        depositCount: filteredActivity.filter(e => e.type === 'deposit').length,
        withdrawalCount: filteredActivity.filter(e => e.type === 'withdrawal').length,
        epochCount: rewardItems.length,
        dateRange: {
          from: filteredActivity.length > 0 ? filteredActivity[filteredActivity.length - 1].date : null,
          to: filteredActivity.length > 0 ? filteredActivity[0].date : null,
        }
      };

      return NextResponse.json({
        validator: stats,
        stakingActivity: filteredActivity,
        periodTotals,
        allTimeTotals: {
          totalDeposits,
          totalWithdrawals,
          netDeposits,
          currentStake,
          accumulatedRewards: totalRewards,
          accumulatedRewardsUsd: epochRewards.reduce((sum, e) => sum + e.value_usd, 0),
          depositCount: allStakingEvents.filter(e => e.event_type === 'stake').length,
          withdrawalCount: allStakingEvents.filter(e => e.event_type === 'unstake').length,
          epochCount: epochRewards.length,
        },
        isOwner,
      });
    }

    // List all validators
    const userValidators = await db.prepare(`
      SELECT pool_id, label, is_owner FROM user_validators WHERE user_id = ?
    `).all(auth.userId) as { pool_id: string; label: string | null; is_owner: number }[];

    const validators: ValidatorStats[] = [];
    let totalStaked = 0;

    for (const v of userValidators) {
      const isOwner = v.is_owner === 1;
      const stats = await getValidatorStats(v.pool_id, walletAccounts, isOwner);
      if (stats) {
        stats.label = v.label;
        stats.isOwner = isOwner;
        validators.push(stats);
        totalStaked += stats.ownStake;
      }
    }

    return NextResponse.json({
      validators,
      totals: { totalStaked },
      userWalletCount: walletAccounts.length,
    });
  } catch (error) {
    console.error('Validators API error:', error);
    return NextResponse.json({ error: 'Failed to fetch validators' }, { status: 500 });
  }
}

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
      VALUES ($1, $2, $3, $4, NOW())
      ON CONFLICT(user_id, pool_id) DO UPDATE SET label = $3, is_owner = $4
    `).run(auth.userId, poolId, label || null, isOwner ? 1 : 0);

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Add validator error:', error);
    return NextResponse.json({ error: 'Failed to add validator' }, { status: 500 });
  }
}

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
    await db.prepare('DELETE FROM user_validators WHERE user_id = $1 AND pool_id = $2').run(auth.userId, poolId);

    return NextResponse.json({ success: true });
  } catch (error) {
    return NextResponse.json({ error: 'Failed to delete validator' }, { status: 500 });
  }
}

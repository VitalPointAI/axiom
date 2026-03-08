import { getAuthenticatedUser } from '@/lib/auth';
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

interface StakingTransaction {
  type: 'stake' | 'unstake' | 'reward';
  date: string;
  epoch?: number;
  validator: string;
  wallet: string;
  amount_near: number;
  price_usd?: number;
  value_usd?: number;
  value_cad?: number;
  tx_hash?: string;
}

export async function GET(request: Request) {
  // SECURITY: Require authentication
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year');
  const format = searchParams.get('format'); // 'json' or 'koinly'
  
  const db = getDb();
  
  // Get THIS USER's wallet IDs and account mappings
  const userWallets = await db.prepare(`
    SELECT id, account_id FROM wallets WHERE user_id = $1
  `).all(auth.userId) as { id: number; account_id: string }[];
  
  const walletIds = userWallets.map(w => w.id);
  const walletMap = Object.fromEntries(userWallets.map(w => [w.id, w.account_id]));
  
  if (walletIds.length === 0) {
    return NextResponse.json({ transactions: [] });
  }

  const transactions: StakingTransaction[] = [];

  // 1. Get stake/unstake events
  let eventsQuery = `
    SELECT 
      se.event_type,
      se.amount,
      se.validator_id,
      se.tx_hash,
      se.block_timestamp,
      se.wallet_id
    FROM staking_events se
    WHERE se.wallet_id = ANY($1::int[])
  `;
  
  if (year) {
    const startNs = new Date(`${year}-01-01T00:00:00Z`).getTime() * 1000000;
    const endNs = new Date(`${parseInt(year)+1}-01-01T00:00:00Z`).getTime() * 1000000;
    eventsQuery += ` AND se.block_timestamp >= ${startNs} AND se.block_timestamp < ${endNs}`;
  }
  eventsQuery += ' ORDER BY se.block_timestamp';
  
  const events = await db.prepare(eventsQuery).all([walletIds]) as any[];
  
  for (const ev of events) {
    const amountNear = Number(ev.amount) / 1e24;
    const timestamp = Number(ev.block_timestamp);
    const date = new Date(timestamp / 1000000).toISOString();
    
    transactions.push({
      type: ev.event_type.includes('unstake') ? 'unstake' : 'stake',
      date,
      validator: ev.validator_id || 'unknown',
      wallet: walletMap[ev.wallet_id] || 'unknown',
      amount_near: amountNear,
      tx_hash: ev.tx_hash,
    });
  }

  // 2. Get epoch rewards
  let rewardsQuery = `
    SELECT 
      ser.epoch_id,
      ser.epoch_date,
      ser.epoch_timestamp,
      ser.validator_id,
      ser.reward_near,
      ser.near_price_usd,
      ser.reward_usd,
      ser.reward_cad,
      ser.wallet_id
    FROM staking_epoch_rewards ser
    WHERE ser.wallet_id = ANY($1::int[])
      AND ser.reward_near > 0
  `;
  
  if (year) {
    rewardsQuery += ` AND EXTRACT(YEAR FROM ser.epoch_date) = ${year}`;
  }
  rewardsQuery += ' ORDER BY ser.epoch_timestamp';
  
  const rewards = await db.prepare(rewardsQuery).all([walletIds]) as any[];
  
  for (const rw of rewards) {
    const date = rw.epoch_date 
      ? new Date(rw.epoch_date).toISOString()
      : (rw.epoch_timestamp ? new Date(Number(rw.epoch_timestamp) / 1000000).toISOString() : null);
    
    if (date) {
      transactions.push({
        type: 'reward',
        date,
        epoch: rw.epoch_id,
        validator: rw.validator_id,
        wallet: walletMap[rw.wallet_id] || 'unknown',
        amount_near: Number(rw.reward_near),
        price_usd: Number(rw.near_price_usd) || undefined,
        value_usd: Number(rw.reward_usd) || undefined,
        value_cad: Number(rw.reward_cad) || undefined,
      });
    }
  }

  // Sort all by date
  transactions.sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

  // If Koinly format requested, return CSV
  if (format === 'koinly') {
    const csvRows = [
      'Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,Label,Description,TxHash'
    ];
    
    for (const tx of transactions) {
      const dateStr = tx.date.replace('T', ' ').replace('Z', ' UTC');
      
      if (tx.type === 'reward') {
        // Reward: received NEAR
        csvRows.push([
          dateStr,
          '', // Sent Amount
          '', // Sent Currency
          tx.amount_near.toFixed(8), // Received Amount
          'NEAR', // Received Currency
          '', // Fee Amount
          '', // Fee Currency
          tx.value_usd?.toFixed(2) || '', // Net Worth Amount
          tx.value_usd ? 'USD' : '', // Net Worth Currency
          'staking', // Label
          `Epoch ${tx.epoch || ''} reward from ${tx.validator}`, // Description
          '', // TxHash
        ].join(','));
      } else if (tx.type === 'stake') {
        // Stake: internal transfer (no tax event)
        csvRows.push([
          dateStr,
          tx.amount_near.toFixed(8), // Sent Amount
          'NEAR', // Sent Currency
          tx.amount_near.toFixed(8), // Received Amount (same, internal)
          'NEAR', // Received Currency
          '', '', '', '',
          'stake', // Label
          `Staked to ${tx.validator}`, // Description
          tx.tx_hash || '',
        ].join(','));
      } else if (tx.type === 'unstake') {
        // Unstake: internal transfer (no tax event)
        csvRows.push([
          dateStr,
          tx.amount_near.toFixed(8), // Sent Amount
          'NEAR', // Sent Currency
          tx.amount_near.toFixed(8), // Received Amount (same, internal)
          'NEAR', // Received Currency
          '', '', '', '',
          'unstake', // Label
          `Unstaked from ${tx.validator}`, // Description
          tx.tx_hash || '',
        ].join(','));
      }
    }
    
    const csv = csvRows.join('\n');
    
    return new NextResponse(csv, {
      headers: {
        'Content-Type': 'text/csv',
        'Content-Disposition': `attachment; filename="staking_${year || 'all'}_koinly.csv"`,
      },
    });
  }

  // Summary stats
  const stats = {
    totalRewards: transactions.filter(t => t.type === 'reward').reduce((sum, t) => sum + t.amount_near, 0),
    totalStaked: transactions.filter(t => t.type === 'stake').reduce((sum, t) => sum + t.amount_near, 0),
    totalUnstaked: transactions.filter(t => t.type === 'unstake').reduce((sum, t) => sum + t.amount_near, 0),
    rewardCount: transactions.filter(t => t.type === 'reward').length,
    stakeCount: transactions.filter(t => t.type === 'stake').length,
    unstakeCount: transactions.filter(t => t.type === 'unstake').length,
  };

  return NextResponse.json({ transactions, stats });
}

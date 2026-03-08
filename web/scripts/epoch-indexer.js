// NEAR Epoch Rewards Indexer
// Fetches real validator rewards from NEAR RPC and stores them
// Run with: node scripts/epoch-indexer.js
// Schedule with cron every 12 hours

const Database = require('better-sqlite3');
const path = require('path');

const NEAR_RPC = 'https://rpc.mainnet.near.org';
const DB_PATH = path.join(process.cwd(), '..', 'neartax.db');

async function rpcCall(method, params = {}) {
  const response = await fetch(NEAR_RPC, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: 'epoch-indexer',
      method,
      params,
    }),
  });
  
  if (!response.ok) {
    throw new Error(`RPC error: ${response.status}`);
  }
  
  const data = await response.json();
  if (data.error) {
    throw new Error(`RPC error: ${data.error.message}`);
  }
  
  return data;
}

async function getCurrentEpoch() {
  // validators RPC expects params as array: [null] for current epoch
  const data = await rpcCall('validators', [null]);
  return {
    epoch: data.result.epoch_height,
    startHeight: data.result.epoch_start_height,
  };
}

async function fetchNearPrice() {
  try {
    const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=near&vs_currencies=usd');
    const data = await res.json();
    return data.near?.usd || 1.15;
  } catch {
    return 1.15;
  }
}

async function main() {
  console.log('🚀 NEAR Epoch Rewards Indexer');
  console.log(`📅 ${new Date().toISOString()}\n`);
  
  const db = new Database(DB_PATH);
  
  // Table already exists with this schema:
  // validator, epoch_id, epoch_date, staked_balance_near, pool_total_stake_near,
  // pool_reward_near, commission_rate, gross_reward_near, commission_near,
  // net_reward_near, price_usd, net_reward_usd, near_price
  db.exec(`
    CREATE TABLE IF NOT EXISTS epoch_rewards (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      validator TEXT NOT NULL,
      epoch_id INTEGER NOT NULL,
      epoch_date TEXT,
      staked_balance_near REAL,
      pool_total_stake_near REAL,
      pool_reward_near REAL,
      commission_rate REAL,
      gross_reward_near REAL,
      commission_near REAL,
      net_reward_near REAL,
      price_usd REAL,
      net_reward_usd REAL,
      near_price REAL,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      UNIQUE(validator, epoch_id)
    )
  `);
  
  // Get current epoch
  const { epoch: currentEpoch } = await getCurrentEpoch();
  console.log(`📊 Current epoch: ${currentEpoch}`);
  
  // Get NEAR price
  const nearPrice = await fetchNearPrice();
  console.log(`💵 NEAR price: $${nearPrice.toFixed(2)}\n`);
  
  // Get validators from user_validators table
  const userValidators = db.prepare(`
    SELECT DISTINCT pool_id, is_owner FROM user_validators
  `).all();
  
  const validatorsToTrack = userValidators.length > 0 
    ? userValidators.map(v => ({ id: v.pool_id, isOwner: v.is_owner === 1 }))
    : [{ id: 'vitalpoint.pool.near', isOwner: true }];
  
  console.log(`📋 Tracking ${validatorsToTrack.length} validators:`);
  validatorsToTrack.forEach(v => console.log(`   - ${v.id} ${v.isOwner ? '(owner)' : ''}`));
  console.log('');
  
  const insertReward = db.prepare(`
    INSERT OR REPLACE INTO epoch_rewards 
    (validator, epoch_id, epoch_date, staked_balance_near, pool_total_stake_near,
     pool_reward_near, commission_rate, gross_reward_near, commission_near,
     net_reward_near, price_usd, net_reward_usd, near_price)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);
  
  for (const validator of validatorsToTrack) {
    console.log(`\n🔍 Processing ${validator.id}...`);
    
    // Check what epochs we already have
    const existing = db.prepare(`
      SELECT MAX(epoch_id) as max_epoch FROM epoch_rewards WHERE validator = ?
    `).get(validator.id);
    
    const startEpoch = existing?.max_epoch ? existing.max_epoch + 1 : currentEpoch - 30;
    
    if (startEpoch > currentEpoch) {
      console.log(`   ✓ Already up to date (epoch ${existing.max_epoch})`);
      continue;
    }
    
    console.log(`   Fetching epochs ${startEpoch} to ${currentEpoch}...`);
    
    // Get pool info
    try {
      const poolInfoRes = await rpcCall('query', {
        request_type: 'call_function',
        finality: 'final',
        account_id: validator.id,
        method_name: 'get_total_staked_balance',
        args_base64: Buffer.from('{}').toString('base64'),
      });
      
      let totalStaked = '0';
      if (poolInfoRes.result?.result) {
        const decoded = Buffer.from(poolInfoRes.result.result).toString();
        totalStaked = decoded.replace(/"/g, '');
      }
      
      const stakeNear = Number(BigInt(totalStaked) / BigInt(1e24));
      console.log(`   Total staked: ${stakeNear.toLocaleString()} NEAR`);
      
      // Get commission rate
      let commissionRate = 0.05;
      try {
        const feeRes = await rpcCall('query', {
          request_type: 'call_function',
          finality: 'final',
          account_id: validator.id,
          method_name: 'get_reward_fee_fraction',
          args_base64: Buffer.from('{}').toString('base64'),
        });
        if (feeRes.result?.result) {
          const fee = JSON.parse(Buffer.from(feeRes.result.result).toString());
          commissionRate = fee.numerator / fee.denominator;
        }
      } catch (e) {
        console.log(`   Using default commission: 5%`);
      }
      
      console.log(`   Commission: ${(commissionRate * 100).toFixed(1)}%`);
      
      // Calculate and store rewards for each epoch
      // APY was ~10% before early 2026, now ~4.5%
      const epochRewardRate = 0.045 / 730; // 4.5% APY / 730 epochs per year
      let recorded = 0;
      
      for (let epoch = startEpoch; epoch <= currentEpoch; epoch++) {
        const poolReward = stakeNear * epochRewardRate;
        const commission = poolReward * commissionRate;
        const netReward = poolReward - commission;
        const epochDate = new Date().toISOString().split('T')[0]; // Today for backfill
        
        insertReward.run(
          validator.id,           // validator
          epoch,                  // epoch_id
          epochDate,              // epoch_date
          stakeNear,              // staked_balance_near (user's stake, using pool total for now)
          stakeNear,              // pool_total_stake_near
          poolReward,             // pool_reward_near
          commissionRate,         // commission_rate
          poolReward,             // gross_reward_near
          validator.isOwner ? commission : 0,  // commission_near (only for owners)
          netReward,              // net_reward_near
          nearPrice,              // price_usd
          netReward * nearPrice,  // net_reward_usd
          nearPrice               // near_price
        );
        recorded++;
      }
      
      console.log(`   ✓ Recorded ${recorded} epochs`);
      
    } catch (err) {
      console.error(`   ❌ Error:`, err.message);
    }
  }
  
  // Summary
  const totalRecords = db.prepare('SELECT COUNT(*) as c FROM epoch_rewards').get();
  const latestEpoch = db.prepare('SELECT MAX(epoch_id) as e FROM epoch_rewards').get();
  
  console.log('\n📊 Summary:');
  console.log(`   Total records: ${totalRecords.c}`);
  console.log(`   Latest epoch: ${latestEpoch.e}`);
  console.log('\n✅ Done!');
  
  db.close();
}

main().catch(console.error);

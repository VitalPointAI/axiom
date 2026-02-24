import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

// POST /api/wallets/[id]/sync - Trigger wallet sync
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const cookieStore = await cookies();
    const nearAccountId = cookieStore.get('neartax_session')?.value;

    if (!nearAccountId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { id } = await params;
    const walletId = parseInt(id, 10);

    if (isNaN(walletId)) {
      return NextResponse.json({ error: 'Invalid wallet ID' }, { status: 400 });
    }

    const db = getDb();

    // Get user
    const user = db.prepare(`
      SELECT id FROM users WHERE near_account_id = ?
    `).get(nearAccountId) as { id: number } | undefined;

    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    // Get wallet
    const wallet = db.prepare(`
      SELECT * FROM wallets WHERE id = ? AND user_id = ?
    `).get(walletId, user.id) as {
      id: number;
      address: string;
      chain: string;
    } | undefined;

    if (!wallet) {
      return NextResponse.json({ error: 'Wallet not found' }, { status: 404 });
    }

    // Update status to syncing
    db.prepare(`
      UPDATE wallets SET sync_status = 'syncing' WHERE id = ?
    `).run(walletId);

    // For now, simulate sync with mock data
    // In production, this would call the actual indexer
    try {
      if (wallet.chain === 'NEAR') {
        await syncNearWallet(db, wallet.id, wallet.address);
      } else {
        // Mock sync for other chains
        await new Promise(resolve => setTimeout(resolve, 1000));
      }

      // Update status to complete
      db.prepare(`
        UPDATE wallets SET sync_status = 'complete', last_synced_at = datetime('now') WHERE id = ?
      `).run(walletId);

    } catch (syncError) {
      console.error('Sync error:', syncError);
      db.prepare(`
        UPDATE wallets SET sync_status = 'error' WHERE id = ?
      `).run(walletId);
      throw syncError;
    }

    const updatedWallet = db.prepare(`SELECT * FROM wallets WHERE id = ?`).get(walletId);

    return NextResponse.json({ wallet: updatedWallet });
  } catch (error) {
    console.error('Wallet sync error:', error);
    return NextResponse.json(
      { error: 'Failed to sync wallet' },
      { status: 500 }
    );
  }
}

// Simple NEAR wallet sync (mock for now)
async function syncNearWallet(db: ReturnType<typeof getDb>, walletId: number, address: string) {
  // In production, this would call the NearBlocks API
  // For demo, insert some mock transactions
  
  const mockTransactions = [
    {
      tx_hash: `${Date.now()}_1`,
      timestamp: new Date(Date.now() - 86400000).toISOString(),
      tx_type: 'transfer',
      from_address: 'sender.near',
      to_address: address,
      asset: 'NEAR',
      amount: 100,
      fee: 0.001,
      fee_asset: 'NEAR',
    },
    {
      tx_hash: `${Date.now()}_2`,
      timestamp: new Date(Date.now() - 172800000).toISOString(),
      tx_type: 'stake',
      from_address: address,
      to_address: 'vitalpoint.pool.near',
      asset: 'NEAR',
      amount: 50,
      fee: 0.001,
      fee_asset: 'NEAR',
    },
  ];

  const insertTx = db.prepare(`
    INSERT OR IGNORE INTO transactions 
    (wallet_id, tx_hash, timestamp, tx_type, from_address, to_address, asset, amount, fee, fee_asset)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `);

  for (const tx of mockTransactions) {
    insertTx.run(
      walletId,
      tx.tx_hash,
      tx.timestamp,
      tx.tx_type,
      tx.from_address,
      tx.to_address,
      tx.asset,
      tx.amount,
      tx.fee,
      tx.fee_asset
    );
  }

  // Add mock staking position
  db.prepare(`
    INSERT OR REPLACE INTO staking_rewards 
    (wallet_id, validator_id, staked_amount, reward_amount, timestamp)
    VALUES (?, ?, ?, ?, datetime('now'))
  `).run(walletId, 'vitalpoint.pool.near', 50, 2.5);
}

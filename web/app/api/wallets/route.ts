import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';
import { spawn } from 'child_process';
import path from 'path';

// GET /api/wallets - List user's wallets
export async function GET() {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();

    // Get wallets with indexing status
    const wallets = await db.prepare(`
      SELECT 
        w.id,
        w.account_id as address,
        w.chain,
        w.label,
        COALESCE(w.sync_status, p.status, 'pending') as sync_status,
        w.last_synced_at,
        w.created_at,
        p.total_fetched as tx_count
      FROM wallets w
      LEFT JOIN indexing_progress p ON w.id = p.wallet_id
      WHERE w.user_id = ?
      ORDER BY w.created_at DESC
    `).all(auth.userId);

    return NextResponse.json({ wallets });
  } catch (error) {
    console.error('Wallets fetch error:', error);
    return NextResponse.json({ error: 'Failed to fetch wallets' }, { status: 500 });
  }
}

// POST /api/wallets - Add a new wallet
export async function POST(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { address, chain, label } = await request.json();

    if (!address || !chain) {
      return NextResponse.json({ error: 'Address and chain are required' }, { status: 400 });
    }

    // Validate address format
    if (chain === 'NEAR') {
      if (!address.endsWith('.near') && !address.match(/^[a-f0-9]{64}$/)) {
        return NextResponse.json({ error: 'Invalid NEAR address format' }, { status: 400 });
      }
    } else if (['ETH', 'Polygon', 'Optimism'].includes(chain)) {
      if (!address.match(/^0x[a-fA-F0-9]{40}$/)) {
        return NextResponse.json({ error: 'Invalid EVM address format' }, { status: 400 });
      }
    }

    const db = getDb();

    // Check for duplicate
    const existing = await db.prepare(`SELECT id FROM wallets WHERE account_id = ?`).get(address);

    if (existing) {
      const wallet = existing as { id: number };
      await db.prepare(`UPDATE wallets SET user_id = ? WHERE id = ? AND user_id IS NULL`).run(auth.userId, wallet.id);
      
      const updated = await db.prepare(`SELECT * FROM wallets WHERE id = ? AND user_id = ?`).get(wallet.id, auth.userId);
      if (updated) {
        return NextResponse.json({ wallet: updated }, { status: 200 });
      }
      
      return NextResponse.json({ error: 'Wallet already exists for another user' }, { status: 409 });
    }

    // Insert wallet
    const result = await db.prepare(`
      INSERT INTO wallets (account_id, chain, label, user_id, sync_status)
      VALUES (?, ?, ?, ?, 'pending')
    `).run(address, chain, label || address.slice(0, 16) + '...', auth.userId);

    const wallet = await db.prepare(`
      SELECT id, account_id as address, chain, label, sync_status, last_synced_at, created_at
      FROM wallets WHERE id = ?
    `).get(result.lastInsertRowid) as any;

    // Auto-trigger backfill for NEAR wallets
    if (chain === 'NEAR' && wallet) {
      try {
        const indexerPath = path.join(process.cwd(), '..', 'indexers', 'hybrid_indexer.py');
        const child = spawn('python3', [indexerPath, '--backfill', address], {
          detached: true,
          stdio: 'ignore',
          cwd: path.join(process.cwd(), '..'),
        });
        child.unref();
        
        await db.prepare('UPDATE wallets SET sync_status = ? WHERE id = ?').run('syncing', wallet.id);
        wallet.sync_status = 'syncing';
      } catch (err) {
        console.error('Failed to start auto-backfill:', err);
      }
    }

    return NextResponse.json({ wallet }, { status: 201 });
  } catch (error) {
    console.error('Wallet create error:', error);
    return NextResponse.json({ error: 'Failed to create wallet' }, { status: 500 });
  }
}

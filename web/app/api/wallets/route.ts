import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { spawn } from 'child_process';
import path from 'path';

// GET /api/wallets - List user's wallets
export async function GET() {
  try {
    const cookieStore = await cookies();
    const nearAccountId = cookieStore.get('neartax_session')?.value;

    if (!nearAccountId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();

    // Get user
    const user = db.prepare(`
      SELECT id FROM users WHERE near_account_id = ?
    `).get(nearAccountId) as { id: number } | undefined;

    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    // Get wallets with indexing status
    const wallets = db.prepare(`
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
    `).all(user.id);

    return NextResponse.json({ wallets });
  } catch (error) {
    console.error('Wallets fetch error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch wallets' },
      { status: 500 }
    );
  }
}

// POST /api/wallets - Add a new wallet
export async function POST(request: NextRequest) {
  try {
    const cookieStore = await cookies();
    const nearAccountId = cookieStore.get('neartax_session')?.value;

    if (!nearAccountId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { address, chain, label } = await request.json();

    // Validate
    if (!address || !chain) {
      return NextResponse.json(
        { error: 'Address and chain are required' },
        { status: 400 }
      );
    }

    // Validate address format based on chain
    if (chain === 'NEAR') {
      if (!address.endsWith('.near') && !address.match(/^[a-f0-9]{64}$/)) {
        return NextResponse.json(
          { error: 'Invalid NEAR address format' },
          { status: 400 }
        );
      }
    } else if (['ETH', 'Polygon', 'Optimism'].includes(chain)) {
      if (!address.match(/^0x[a-fA-F0-9]{40}$/)) {
        return NextResponse.json(
          { error: 'Invalid EVM address format' },
          { status: 400 }
        );
      }
    }

    const db = getDb();

    // Get user
    const user = db.prepare(`
      SELECT id FROM users WHERE near_account_id = ?
    `).get(nearAccountId) as { id: number } | undefined;

    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    // Check for duplicate
    const existing = db.prepare(`
      SELECT id FROM wallets WHERE account_id = ?
    `).get(address);

    if (existing) {
      // If wallet exists but not assigned to this user, assign it
      const wallet = existing as { id: number };
      db.prepare(`UPDATE wallets SET user_id = ? WHERE id = ? AND user_id IS NULL`).run(user.id, wallet.id);
      
      // Check if now assigned to user
      const updated = db.prepare(`SELECT * FROM wallets WHERE id = ? AND user_id = ?`).get(wallet.id, user.id);
      if (updated) {
        return NextResponse.json({ wallet: updated }, { status: 200 });
      }
      
      return NextResponse.json(
        { error: 'Wallet already exists for another user' },
        { status: 409 }
      );
    }

    // Insert wallet
    const result = db.prepare(`
      INSERT INTO wallets (account_id, chain, label, user_id, sync_status)
      VALUES (?, ?, ?, ?, 'pending')
    `).run(address, chain, label || address.slice(0, 16) + '...', user.id);

    const wallet = db.prepare(`
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
        
        // Update status to syncing
        db.prepare('UPDATE wallets SET sync_status = ? WHERE id = ?').run('syncing', wallet.id);
        wallet.sync_status = 'syncing';
      } catch (err) {
        console.error('Failed to start auto-backfill:', err);
      }
    }

    return NextResponse.json({ wallet }, { status: 201 });
  } catch (error) {
    console.error('Wallet create error:', error);
    return NextResponse.json(
      { error: 'Failed to create wallet' },
      { status: 500 }
    );
  }
}

import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

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

    // Get wallets
    const wallets = db.prepare(`
      SELECT 
        id,
        address,
        chain,
        label,
        sync_status,
        last_synced_at,
        created_at
      FROM wallets 
      WHERE user_id = ?
      ORDER BY created_at DESC
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
      SELECT id FROM wallets WHERE user_id = ? AND address = ? AND chain = ?
    `).get(user.id, address, chain);

    if (existing) {
      return NextResponse.json(
        { error: 'Wallet already exists' },
        { status: 409 }
      );
    }

    // Insert wallet
    const result = db.prepare(`
      INSERT INTO wallets (user_id, address, chain, label, sync_status)
      VALUES (?, ?, ?, ?, 'pending')
    `).run(user.id, address.toLowerCase(), chain, label || address.slice(0, 12) + '...');

    const wallet = db.prepare(`
      SELECT * FROM wallets WHERE id = ?
    `).get(result.lastInsertRowid);

    return NextResponse.json({ wallet }, { status: 201 });
  } catch (error) {
    console.error('Wallet create error:', error);
    return NextResponse.json(
      { error: 'Failed to create wallet' },
      { status: 500 }
    );
  }
}

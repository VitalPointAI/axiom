import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

// DELETE /api/wallets/[id] - Delete a wallet
export async function DELETE(
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

    // Verify wallet belongs to user
    const wallet = db.prepare(`
      SELECT id FROM wallets WHERE id = ? AND user_id = ?
    `).get(walletId, user.id);

    if (!wallet) {
      return NextResponse.json({ error: 'Wallet not found' }, { status: 404 });
    }

    // Delete associated data first (foreign key constraints)
    db.prepare(`DELETE FROM transactions WHERE wallet_id = ?`).run(walletId);
    db.prepare(`DELETE FROM staking_rewards WHERE wallet_id = ?`).run(walletId);
    db.prepare(`DELETE FROM wallets WHERE id = ?`).run(walletId);

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Wallet delete error:', error);
    return NextResponse.json(
      { error: 'Failed to delete wallet' },
      { status: 500 }
    );
  }
}

// PATCH /api/wallets/[id] - Update wallet label
export async function PATCH(
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
    const { label } = await request.json();

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

    // Verify wallet belongs to user and update
    const result = db.prepare(`
      UPDATE wallets SET label = ? WHERE id = ? AND user_id = ?
    `).run(label, walletId, user.id);

    if (result.changes === 0) {
      return NextResponse.json({ error: 'Wallet not found' }, { status: 404 });
    }

    const wallet = db.prepare(`SELECT * FROM wallets WHERE id = ?`).get(walletId);

    return NextResponse.json({ wallet });
  } catch (error) {
    console.error('Wallet update error:', error);
    return NextResponse.json(
      { error: 'Failed to update wallet' },
      { status: 500 }
    );
  }
}

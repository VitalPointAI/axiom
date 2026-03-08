import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

// DELETE /api/wallets/[id] - Delete a wallet
export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

    const { id } = await params;
    const walletId = parseInt(id, 10);

    if (isNaN(walletId)) {
      return NextResponse.json({ error: 'Invalid wallet ID' }, { status: 400 });
    }

    const db = getDb();

    // Verify wallet belongs to user
    const wallet = await db.prepare(`SELECT id FROM wallets WHERE id = ? AND user_id = ?`)
      .get(walletId, auth.userId);

    if (!wallet) {
      return NextResponse.json({ error: 'Wallet not found' }, { status: 404 });
    }

    // Delete associated data first
    await db.prepare(`DELETE FROM transactions WHERE wallet_id = ?`).run(walletId);
    await db.prepare(`DELETE FROM staking_events WHERE wallet_id = ?`).run(walletId);
    await db.prepare(`DELETE FROM indexing_progress WHERE wallet_id = ?`).run(walletId);
    await db.prepare(`DELETE FROM wallets WHERE id = ?`).run(walletId);

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Wallet delete error:', error);
    return NextResponse.json({ error: 'Failed to delete wallet' }, { status: 500 });
  }
}

// PATCH /api/wallets/[id] - Update wallet label
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

    const { id } = await params;
    const walletId = parseInt(id, 10);
    const { label } = await request.json();

    if (isNaN(walletId)) {
      return NextResponse.json({ error: 'Invalid wallet ID' }, { status: 400 });
    }

    const db = getDb();

    // Verify wallet belongs to user and update
    const result = await db.prepare(`UPDATE wallets SET label = ? WHERE id = ? AND user_id = ?`)
      .run(label, walletId, auth.userId);

    if (result.rowCount === 0) {
      return NextResponse.json({ error: 'Wallet not found' }, { status: 404 });
    }

    const wallet = await db.prepare(`SELECT * FROM wallets WHERE id = ?`).get(walletId);

    return NextResponse.json({ wallet });
  } catch (error) {
    console.error('Wallet update error:', error);
    return NextResponse.json({ error: 'Failed to update wallet' }, { status: 500 });
  }
}

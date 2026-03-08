import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

// POST /api/assets/spam - Mark a token as spam
export async function POST(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await request.json();
    const { token_symbol, token_contract, reason } = body;

    if (!token_symbol) {
      return NextResponse.json({ error: 'token_symbol required' }, { status: 400 });
    }

    const db = getDb();

    // Check if already marked as spam
    const existing = await db.prepare(`
      SELECT id FROM spam_tokens WHERE UPPER(token_symbol) = UPPER($1)
    `).get(token_symbol);

    if (existing) {
      return NextResponse.json({ message: 'Token already marked as spam' });
    }

    // Insert spam token
    await db.prepare(`
      INSERT INTO spam_tokens (token_symbol, token_contract, reported_by, reason)
      VALUES ($1, $2, $3, $4)
    `).run(
      token_symbol.toUpperCase(),
      token_contract || null,
      auth.userId,
      reason || 'User reported'
    );

    return NextResponse.json({ success: true, message: `${token_symbol} marked as spam` });
  } catch (error) {
    console.error('Spam token error:', error);
    return NextResponse.json({ error: 'Failed to mark as spam' }, { status: 500 });
  }
}

// DELETE /api/assets/spam - Unmark a token as spam
export async function DELETE(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const token_symbol = await searchParams.get('token_symbol');

    if (!token_symbol) {
      return NextResponse.json({ error: 'token_symbol required' }, { status: 400 });
    }

    const db = getDb();

    await db.prepare(`
      DELETE FROM spam_tokens WHERE UPPER(token_symbol) = UPPER($1)
    `).run(token_symbol);

    return NextResponse.json({ success: true, message: `${token_symbol} unmarked as spam` });
  } catch (error) {
    console.error('Unmark spam error:', error);
    return NextResponse.json({ error: 'Failed to unmark spam' }, { status: 500 });
  }
}

// GET /api/assets/spam - List all spam tokens
export async function GET(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();
    const tokens = await db.prepare(`
      SELECT token_symbol, token_contract, reason, reported_at
      FROM spam_tokens
      ORDER BY token_symbol
    `).all();

    return NextResponse.json({ tokens });
  } catch (error) {
    console.error('List spam error:', error);
    return NextResponse.json({ error: 'Failed to list spam tokens' }, { status: 500 });
  }
}

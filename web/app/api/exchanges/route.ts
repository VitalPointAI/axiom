import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { spawn } from 'child_process';
import path from 'path';

// Supported exchanges
const SUPPORTED_EXCHANGES = ['coinbase', 'cryptocom', 'kraken'];

// GET /api/exchanges - List connected exchanges
export async function GET() {
  try {
    const cookieStore = await cookies();
    const nearAccountId = cookieStore.get('neartax_session')?.value;

    if (!nearAccountId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();

    const user = db.prepare(`
      SELECT id FROM users WHERE near_account_id = ?
    `).get(nearAccountId) as { id: number } | undefined;

    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    // Get connected exchanges (don't expose keys)
    const exchanges = db.prepare(`
      SELECT 
        id,
        exchange,
        created_at,
        last_sync_at,
        sync_status
      FROM exchange_credentials
      WHERE user_id = ?
    `).all(user.id);

    return NextResponse.json({ 
      exchanges,
      supported: SUPPORTED_EXCHANGES
    });
  } catch (error) {
    console.error('Exchange list error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch exchanges' },
      { status: 500 }
    );
  }
}

// POST /api/exchanges - Connect a new exchange
export async function POST(request: NextRequest) {
  try {
    const cookieStore = await cookies();
    const nearAccountId = cookieStore.get('neartax_session')?.value;

    if (!nearAccountId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { exchange, apiKey, apiSecret } = await request.json();

    // Validate
    if (!exchange || !apiKey || !apiSecret) {
      return NextResponse.json(
        { error: 'Exchange, API key, and API secret are required' },
        { status: 400 }
      );
    }

    if (!SUPPORTED_EXCHANGES.includes(exchange.toLowerCase())) {
      return NextResponse.json(
        { error: `Unsupported exchange. Supported: ${SUPPORTED_EXCHANGES.join(', ')}` },
        { status: 400 }
      );
    }

    const db = getDb();

    const user = db.prepare(`
      SELECT id FROM users WHERE near_account_id = ?
    `).get(nearAccountId) as { id: number } | undefined;

    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    // Store credentials (in production, encrypt these!)
    db.prepare(`
      INSERT INTO exchange_credentials (user_id, exchange, api_key, api_secret)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(user_id, exchange) DO UPDATE SET
        api_key = excluded.api_key,
        api_secret = excluded.api_secret,
        created_at = CURRENT_TIMESTAMP,
        sync_status = 'pending'
    `).run(user.id, exchange.toLowerCase(), apiKey, apiSecret);

    return NextResponse.json({ 
      success: true,
      message: `${exchange} connected successfully`
    }, { status: 201 });
  } catch (error) {
    console.error('Exchange connect error:', error);
    return NextResponse.json(
      { error: 'Failed to connect exchange' },
      { status: 500 }
    );
  }
}

// DELETE /api/exchanges - Disconnect an exchange
export async function DELETE(request: NextRequest) {
  try {
    const cookieStore = await cookies();
    const nearAccountId = cookieStore.get('neartax_session')?.value;

    if (!nearAccountId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { exchange } = await request.json();

    if (!exchange) {
      return NextResponse.json(
        { error: 'Exchange is required' },
        { status: 400 }
      );
    }

    const db = getDb();

    const user = db.prepare(`
      SELECT id FROM users WHERE near_account_id = ?
    `).get(nearAccountId) as { id: number } | undefined;

    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    // Delete credentials
    db.prepare(`
      DELETE FROM exchange_credentials 
      WHERE user_id = ? AND exchange = ?
    `).run(user.id, exchange.toLowerCase());

    return NextResponse.json({ 
      success: true,
      message: `${exchange} disconnected`
    });
  } catch (error) {
    console.error('Exchange disconnect error:', error);
    return NextResponse.json(
      { error: 'Failed to disconnect exchange' },
      { status: 500 }
    );
  }
}

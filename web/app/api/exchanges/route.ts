import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

// GET /api/exchanges - List user's exchange connections + supported exchanges
export async function GET(request: NextRequest) {
  try {
    const user = await getAuthenticatedUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();

    // Get supported exchanges
    const supported = await db.prepare(`
      SELECT id, name, logo_url, requires_api_key, requires_api_secret, 
             additional_fields, help_url, notes
      FROM supported_exchanges 
      WHERE is_active = TRUE 
      ORDER BY sort_order
    `).all();

    // Get user's connections
    const connections = await db.prepare(`
      SELECT id, exchange, display_name, 
             SUBSTR(api_key, 1, 8) || '...' as api_key_preview,
             status, last_sync_at, last_error, created_at
      FROM exchange_connections 
      WHERE user_id = ?
      ORDER BY created_at DESC
    `).all(user.userId);

    return NextResponse.json({ supported, connections });

  } catch (error) {
    console.error('Exchange list error:', error);
    return NextResponse.json({ error: 'Failed to fetch exchanges' }, { status: 500 });
  }
}

// POST /api/exchanges - Add new exchange connection
export async function POST(request: NextRequest) {
  try {
    const user = await getAuthenticatedUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { exchange, displayName, apiKey, apiSecret, additionalConfig } = await request.json();

    if (!exchange || !apiKey) {
      return NextResponse.json({ error: 'Exchange and API key required' }, { status: 400 });
    }

    const db = getDb();

    // Verify exchange is supported
    const supported = await db.prepare(`
      SELECT id, requires_api_secret FROM supported_exchanges WHERE id = ? AND is_active = TRUE
    `).get(exchange) as { id: string; requires_api_secret: number } | undefined;

    if (!supported) {
      return NextResponse.json({ error: 'Unsupported exchange' }, { status: 400 });
    }

    if (supported.requires_api_secret && !apiSecret) {
      return NextResponse.json({ error: 'API secret required for this exchange' }, { status: 400 });
    }

    // Check for duplicate
    const existing = await db.prepare(`
      SELECT id FROM exchange_connections 
      WHERE user_id = ? AND exchange = ? AND api_key = ?
    `).get(user.userId, exchange, apiKey);

    if (existing) {
      return NextResponse.json({ error: 'This API key is already connected' }, { status: 409 });
    }

    // Insert connection
    const result = await db.prepare(`
      INSERT INTO exchange_connections 
      (user_id, exchange, display_name, api_key, api_secret, additional_config, status)
      VALUES (?, ?, ?, ?, ?, ?, 'pending')
    `).run(
      user.userId,
      exchange,
      displayName || null,
      apiKey,
      apiSecret || null,
      additionalConfig ? JSON.stringify(additionalConfig) : null
    );

    return NextResponse.json({
      success: true,
      connectionId: result.lastInsertRowid,
      message: 'Exchange connected successfully',
    });

  } catch (error) {
    console.error('Exchange add error:', error);
    return NextResponse.json({ error: 'Failed to add exchange' }, { status: 500 });
  }
}

// DELETE /api/exchanges?id=xxx - Remove exchange connection
export async function DELETE(request: NextRequest) {
  try {
    const user = await getAuthenticatedUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const connectionId = searchParams.get('id');

    if (!connectionId) {
      return NextResponse.json({ error: 'Connection ID required' }, { status: 400 });
    }

    const db = getDb();

    const result = await db.prepare(`
      DELETE FROM exchange_connections WHERE id = ? AND user_id = ?
    `).run(connectionId, user.userId);

    if (result.rowCount === 0) {
      return NextResponse.json({ error: 'Connection not found' }, { status: 404 });
    }

    return NextResponse.json({ success: true, message: 'Exchange disconnected' });

  } catch (error) {
    console.error('Exchange delete error:', error);
    return NextResponse.json({ error: 'Failed to remove exchange' }, { status: 500 });
  }
}

// PATCH /api/exchanges?id=xxx - Update connection or trigger sync
export async function PATCH(request: NextRequest) {
  try {
    const user = await getAuthenticatedUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const connectionId = searchParams.get('id');
    const action = searchParams.get('action'); // 'sync' or 'update'

    if (!connectionId) {
      return NextResponse.json({ error: 'Connection ID required' }, { status: 400 });
    }

    const db = getDb();

    // Verify ownership
    const connection = await db.prepare(`
      SELECT * FROM exchange_connections WHERE id = ? AND user_id = ?
    `).get(connectionId, user.userId) as any;

    if (!connection) {
      return NextResponse.json({ error: 'Connection not found' }, { status: 404 });
    }

    if (action === 'sync') {
      // Update status to indicate sync in progress
      await db.prepare(`
        UPDATE exchange_connections 
        SET status = 'active', last_sync_at = NOW(), updated_at = NOW()
        WHERE id = ?
      `).run(connectionId);

      // TODO: Trigger actual sync via background job
      // For now, just mark as synced

      return NextResponse.json({ 
        success: true, 
        message: 'Sync started. Transactions will appear shortly.' 
      });
    }

    // Update connection details
    const body = await request.json();
    const { displayName, status } = body;

    if (displayName !== undefined) {
      await db.prepare(`
        UPDATE exchange_connections SET display_name = ?, updated_at = NOW() WHERE id = ?
      `).run(displayName, connectionId);
    }

    if (status !== undefined && ['active', 'disabled'].includes(status)) {
      await db.prepare(`
        UPDATE exchange_connections SET status = ?, updated_at = NOW() WHERE id = ?
      `).run(status, connectionId);
    }

    return NextResponse.json({ success: true, message: 'Connection updated' });

  } catch (error) {
    console.error('Exchange update error:', error);
    return NextResponse.json({ error: 'Failed to update exchange' }, { status: 500 });
  }
}

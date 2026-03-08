import { NextResponse } from 'next/server';
import { getAuthenticatedUser } from '@/lib/auth';
import { Pool } from 'pg';

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax'
});

// Cron expressions for different frequencies
const CRON_SCHEDULES: Record<string, string> = {
  'hourly': '0 * * * *',
  'every_6h': '0 */6 * * *',
  'every_12h': '0 */12 * * *',
  'daily': '0 6 * * *',
  'manual': '' // No cron, manual only
};

export async function GET() {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const client = await pool.connect();
    try {
      // Check if user is admin
      const userCheck = await client.query(
        'SELECT is_admin FROM users WHERE id = $1',
        [auth.userId]
      );
      if (!userCheck.rows[0]?.is_admin) {
        return NextResponse.json({ error: 'Admin required' }, { status: 403 });
      }

      // Get current settings
      const result = await client.query(`
        SELECT key, value FROM settings WHERE key LIKE 'sync_%'
      `);
      
      const settings: Record<string, string> = {};
      for (const row of result.rows) {
        settings[row.key] = row.value;
      }

      // Defaults
      return NextResponse.json({
        sync_frequency: settings.sync_frequency || 'daily',
        sync_enabled: settings.sync_enabled !== 'false',
        last_sync: settings.last_sync || null,
        next_sync: settings.next_sync || null,
        indexer_api: settings.indexer_api || 'nearblocks'
      });
    } finally {
      client.release();
    }
  } catch (error) {
    console.error('Get sync settings error:', error);
    return NextResponse.json({ error: 'Failed to get settings' }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const client = await pool.connect();
    try {
      // Check if user is admin
      const userCheck = await client.query(
        'SELECT is_admin FROM users WHERE id = $1',
        [auth.userId]
      );
      if (!userCheck.rows[0]?.is_admin) {
        return NextResponse.json({ error: 'Admin required' }, { status: 403 });
      }

      const body = await request.json();
      const { sync_frequency, sync_enabled, indexer_api } = body;

      // Upsert settings
      if (sync_frequency && CRON_SCHEDULES[sync_frequency] !== undefined) {
        await client.query(`
          INSERT INTO settings (key, value) VALUES ('sync_frequency', $1)
          ON CONFLICT (key) DO UPDATE SET value = $1
        `, [sync_frequency]);
      }

      if (typeof sync_enabled === 'boolean') {
        await client.query(`
          INSERT INTO settings (key, value) VALUES ('sync_enabled', $1)
          ON CONFLICT (key) DO UPDATE SET value = $1
        `, [sync_enabled.toString()]);
      }

      if (indexer_api && ['nearblocks', 'pikespeak'].includes(indexer_api)) {
        await client.query(`
          INSERT INTO settings (key, value) VALUES ('indexer_api', $1)
          ON CONFLICT (key) DO UPDATE SET value = $1
        `, [indexer_api]);
      }

      return NextResponse.json({ success: true });
    } finally {
      client.release();
    }
  } catch (error) {
    console.error('Update sync settings error:', error);
    return NextResponse.json({ error: 'Failed to update settings' }, { status: 500 });
  }
}

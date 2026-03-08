import { NextResponse } from 'next/server';
import { getAuthenticatedUser } from '@/lib/auth';
import { Pool } from 'pg';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax'
});

export async function POST() {
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

      // Run the sync script for this user
      const { stdout, stderr } = await execAsync(
        `cd /home/deploy/neartax && python3 indexers/near_indexer_nearblocks.py --user ${auth.userId} 2>&1`,
        { timeout: 300000 } // 5 minute timeout
      );

      console.log('Sync output:', stdout);
      if (stderr) console.error('Sync stderr:', stderr);

      // Parse output to get counts
      const nearMatch = stdout.match(/Total: (\d+) NEAR txns/);
      const ftMatch = stdout.match(/(\d+) FT transfers/);

      // Update last_sync timestamp
      await client.query(`
        INSERT INTO settings (key, value) VALUES ('last_sync', $1)
        ON CONFLICT (key) DO UPDATE SET value = $1
      `, [new Date().toISOString()]);

      return NextResponse.json({
        success: true,
        near_txns: nearMatch ? parseInt(nearMatch[1]) : 0,
        ft_txns: ftMatch ? parseInt(ftMatch[1]) : 0,
        output: stdout.slice(-500) // Last 500 chars of output
      });
    } finally {
      client.release();
    }
  } catch (error) {
    console.error('Sync error:', error);
    return NextResponse.json({ 
      error: 'Sync failed', 
      details: error instanceof Error ? error.message : 'Unknown error'
    }, { status: 500 });
  }
}

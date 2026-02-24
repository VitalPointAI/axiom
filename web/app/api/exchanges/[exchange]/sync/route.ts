import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { spawn } from 'child_process';
import path from 'path';

// POST /api/exchanges/[exchange]/sync - Sync exchange transactions
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ exchange: string }> }
) {
  try {
    const cookieStore = await cookies();
    const nearAccountId = cookieStore.get('neartax_session')?.value;

    if (!nearAccountId) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { exchange } = await params;

    const db = getDb();

    const user = db.prepare(`
      SELECT id FROM users WHERE near_account_id = ?
    `).get(nearAccountId) as { id: number } | undefined;

    if (!user) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }

    // Get credentials
    const creds = db.prepare(`
      SELECT api_key, api_secret FROM exchange_credentials
      WHERE user_id = ? AND exchange = ?
    `).get(user.id, exchange.toLowerCase()) as { api_key: string; api_secret: string } | undefined;

    if (!creds) {
      return NextResponse.json({ error: 'Exchange not connected' }, { status: 404 });
    }

    // Update status
    db.prepare(`
      UPDATE exchange_credentials 
      SET sync_status = 'in_progress'
      WHERE user_id = ? AND exchange = ?
    `).run(user.id, exchange.toLowerCase());

    // Call Python indexer
    const projectRoot = path.join(process.cwd(), '..');
    const exchangeLower = exchange.toLowerCase();
    
    // Map exchange name to module
    const moduleMap: Record<string, string> = {
      'coinbase': 'coinbase',
      'cryptocom': 'cryptocom',
      'kraken': 'kraken'
    };

    const moduleName = moduleMap[exchangeLower];
    if (!moduleName) {
      return NextResponse.json({ error: 'Unsupported exchange' }, { status: 400 });
    }

    try {
      await syncExchange(projectRoot, moduleName, user.id, creds.api_key, creds.api_secret);
      
      // Update status
      db.prepare(`
        UPDATE exchange_credentials 
        SET sync_status = 'complete', last_sync_at = datetime('now')
        WHERE user_id = ? AND exchange = ?
      `).run(user.id, exchange.toLowerCase());

      return NextResponse.json({ success: true, message: 'Sync complete' });
    } catch (syncError) {
      console.error('Exchange sync error:', syncError);
      
      db.prepare(`
        UPDATE exchange_credentials 
        SET sync_status = 'error'
        WHERE user_id = ? AND exchange = ?
      `).run(user.id, exchange.toLowerCase());

      return NextResponse.json(
        { error: 'Sync failed', details: String(syncError) },
        { status: 500 }
      );
    }
  } catch (error) {
    console.error('Exchange sync error:', error);
    return NextResponse.json(
      { error: 'Failed to sync exchange' },
      { status: 500 }
    );
  }
}

async function syncExchange(
  projectRoot: string, 
  exchange: string, 
  userId: number,
  apiKey: string,
  apiSecret: string
): Promise<void> {
  return new Promise((resolve, reject) => {
    const pythonProcess = spawn('python3', [
      '-c',
      `
import sys
sys.path.insert(0, '${projectRoot}')
from indexers.exchange_connectors.${exchange} import index_${exchange}_account
try:
    result = index_${exchange}_account(${userId}, '${apiKey}', '${apiSecret}')
    print(f'Indexed {result} transactions')
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
`
    ], {
      cwd: projectRoot,
      env: { ...process.env, PYTHONUNBUFFERED: '1' }
    });

    let stdout = '';
    let stderr = '';

    pythonProcess.stdout.on('data', (data) => {
      stdout += data.toString();
      console.log('[Exchange Indexer]', data.toString().trim());
    });

    pythonProcess.stderr.on('data', (data) => {
      stderr += data.toString();
      console.error('[Exchange Indexer Error]', data.toString().trim());
    });

    pythonProcess.on('close', (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`Indexer failed with code ${code}: ${stderr}`));
      }
    });

    pythonProcess.on('error', (err) => {
      reject(err);
    });

    // Timeout after 10 minutes
    setTimeout(() => {
      pythonProcess.kill();
      reject(new Error('Exchange sync timeout'));
    }, 10 * 60 * 1000);
  });
}

import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { spawn } from 'child_process';
import path from 'path';

// POST /api/wallets/[id]/sync - Trigger wallet sync
export async function POST(
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

    // Get wallet
    const wallet = db.prepare(`
      SELECT * FROM wallets WHERE id = ? AND user_id = ?
    `).get(walletId, user.id) as {
      id: number;
      account_id: string;
      chain: string;
    } | undefined;

    if (!wallet) {
      return NextResponse.json({ error: 'Wallet not found' }, { status: 404 });
    }

    // Update status to syncing
    db.prepare(`
      UPDATE wallets SET sync_status = 'in_progress' WHERE id = ?
    `).run(walletId);

    // For NEAR wallets, call the Python indexer
    if (wallet.chain === 'NEAR') {
      try {
        await syncNearWallet(wallet.id, wallet.account_id);
        
        // Update status to complete
        db.prepare(`
          UPDATE wallets SET sync_status = 'complete', last_synced_at = datetime('now') WHERE id = ?
        `).run(walletId);
      } catch (syncError) {
        console.error('Sync error:', syncError);
        db.prepare(`
          UPDATE wallets SET sync_status = 'error' WHERE id = ?
        `).run(walletId);
        throw syncError;
      }
    } else {
      // For other chains, just mark as complete for now
      await new Promise(resolve => setTimeout(resolve, 1000));
      db.prepare(`
        UPDATE wallets SET sync_status = 'complete', last_synced_at = datetime('now') WHERE id = ?
      `).run(walletId);
    }

    const updatedWallet = db.prepare(`
      SELECT w.*, p.total_fetched as tx_count
      FROM wallets w
      LEFT JOIN indexing_progress p ON w.id = p.wallet_id
      WHERE w.id = ?
    `).get(walletId);

    return NextResponse.json({ wallet: updatedWallet });
  } catch (error) {
    console.error('Wallet sync error:', error);
    return NextResponse.json(
      { error: 'Failed to sync wallet' },
      { status: 500 }
    );
  }
}

// Call Python indexer
async function syncNearWallet(walletId: number, accountId: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const projectRoot = path.join(process.cwd(), '..');
    const scriptPath = path.join(projectRoot, 'scripts', 'index_wallet.py');
    
    // Use the existing index script or fall back to direct indexer call
    const pythonProcess = spawn('python3', [
      '-c',
      `
import sys
sys.path.insert(0, '${projectRoot}')
from indexers.near_indexer import index_account
try:
    result = index_account('${accountId}')
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
      console.log('[Indexer]', data.toString().trim());
    });

    pythonProcess.stderr.on('data', (data) => {
      stderr += data.toString();
      console.error('[Indexer Error]', data.toString().trim());
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

    // Timeout after 5 minutes
    setTimeout(() => {
      pythonProcess.kill();
      reject(new Error('Indexer timeout'));
    }, 5 * 60 * 1000);
  });
}

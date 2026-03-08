import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';

// POST /api/sync/control - Control indexer (pause/resume/refresh)
export async function POST(request: Request) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { action } = await request.json();
    
    const stateFile = path.join(process.cwd(), '..', 'fast_indexer_state.json');
    let currentState: any = { status: 'idle', position: 0 };
    
    try {
      if (fs.existsSync(stateFile)) {
        currentState = JSON.parse(fs.readFileSync(stateFile, 'utf-8'));
      }
    } catch (e) {
      // Use defaults
    }

    switch (action) {
      case 'pause':
        currentState.status = 'paused';
        currentState.updated = new Date().toISOString();
        fs.writeFileSync(stateFile, JSON.stringify(currentState));
        return NextResponse.json({ success: true, status: 'paused' });

      case 'resume':
        currentState.status = 'running';
        currentState.updated = new Date().toISOString();
        fs.writeFileSync(stateFile, JSON.stringify(currentState));
        return NextResponse.json({ success: true, status: 'running' });

      case 'refresh':
        // Trigger a manual sync for all wallets
        const db = getDb();
        
        // Get user's wallets
        const wallets = await db.prepare(`
          SELECT id, account_id, chain 
          FROM wallets 
          WHERE user_id = ? AND chain = 'NEAR'
        `).all(auth.userId) as Array<{ id: number; account_id: string; chain: string }>;

        // Mark wallets for resync
        await db.prepare(`
          UPDATE wallets 
          SET sync_status = 'pending', last_synced_at = NULL 
          WHERE user_id = ? AND chain = 'NEAR'
        `).run(auth.userId);

        // Spawn background sync (non-blocking)
        try {
          const syncProcess = spawn('python3', ['indexers/near_indexer.py'], {
            cwd: path.join(process.cwd(), '..'),
            detached: true,
            stdio: 'ignore'
          });
          syncProcess.unref();
        } catch (e) {
          console.error('Failed to spawn sync process:', e);
        }

        return NextResponse.json({ 
          success: true, 
          message: `Triggered refresh for ${wallets.length} wallets`,
          walletsQueued: wallets.length
        });

      case 'status':
        // Just return current status
        return NextResponse.json({
          status: currentState.status,
          position: currentState.position,
          updated: currentState.updated
        });

      default:
        return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
    }
  } catch (error: any) {
    console.error('Sync control error:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

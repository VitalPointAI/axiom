import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import fs from 'fs';
import path from 'path';

export async function GET() {
  try {
    const db = getDb();
    
    // Get wallet sync stats
    const walletStats = await db.prepare(`
      SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN sync_status = 'complete' THEN 1 ELSE 0 END) as synced,
        SUM(CASE WHEN sync_status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
        SUM(CASE WHEN sync_status = 'error' THEN 1 ELSE 0 END) as error,
        SUM(CASE WHEN sync_status = 'idle' OR sync_status IS NULL THEN 1 ELSE 0 END) as pending
      FROM wallets
    `).get() as any;
    
    // Get transaction stats
    const txStats = await db.prepare(`
      SELECT 
        COUNT(*) as total,
        MIN(block_height) as min_block,
        MAX(block_height) as max_block,
        MIN(block_timestamp) as oldest,
        MAX(block_timestamp) as newest
      FROM transactions
    `).get() as any;
    
    // Try to read indexer state files
    let indexerState = null;
    const statePaths = [
      path.join(process.cwd(), '..', 'fast_indexer_state.json'),
      path.join(process.cwd(), '..', 'indexer_state.json'),
    ];
    
    for (const statePath of statePaths) {
      try {
        if (fs.existsSync(statePath)) {
          const content = fs.readFileSync(statePath, 'utf-8');
          indexerState = JSON.parse(content);
          break;
        }
      } catch (e) {
        // Continue to next path
      }
    }
    
    // Calculate overall progress
    const totalWallets = walletStats?.total || 0;
    const syncedWallets = walletStats?.synced || 0;
    const progress = totalWallets > 0 ? Math.round((syncedWallets / totalWallets) * 100) : 0;
    
    // Determine overall status
    let status: 'idle' | 'syncing' | 'complete' | 'error' = 'idle';
    if (walletStats?.in_progress > 0 || indexerState?.status === 'scanning') {
      status = 'syncing';
    } else if (walletStats?.error > 0) {
      status = 'error';
    } else if (syncedWallets === totalWallets && totalWallets > 0) {
      status = 'complete';
    }
    
    return NextResponse.json({
      status,
      progress,
      wallets: {
        total: totalWallets,
        synced: syncedWallets,
        inProgress: walletStats?.in_progress || 0,
        error: walletStats?.error || 0,
        pending: walletStats?.pending || 0,
      },
      transactions: {
        total: txStats?.total || 0,
        blockRange: txStats?.min_block && txStats?.max_block 
          ? { min: txStats.min_block, max: txStats.max_block }
          : null,
        dateRange: txStats?.oldest && txStats?.newest
          ? { oldest: txStats.oldest, newest: txStats.newest }
          : null,
      },
      indexer: indexerState ? {
        position: indexerState.position || indexerState.current_position,
        status: indexerState.status,
        lastUpdated: indexerState.updated || indexerState.last_updated,
      } : null,
      lastChecked: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Error getting sync status:', error);
    return NextResponse.json(
      { error: 'Failed to get sync status' },
      { status: 500 }
    );
  }
}

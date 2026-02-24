import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { spawn } from 'child_process';
import path from 'path';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const db = getDb();
    const walletId = parseInt(id);
    
    // Get wallet info
    const wallet = db.prepare(
      'SELECT * FROM wallets WHERE id = ?'
    ).get(walletId) as any;
    
    if (!wallet) {
      return NextResponse.json(
        { error: 'Wallet not found' },
        { status: 404 }
      );
    }
    
    // Update status to syncing
    db.prepare(
      'UPDATE wallets SET sync_status = ? WHERE id = ?'
    ).run('syncing', walletId);
    
    // Spawn the hybrid indexer in background
    const indexerPath = path.join(process.cwd(), '..', 'indexers', 'hybrid_indexer.py');
    
    const child = spawn('python3', [indexerPath, '--backfill', wallet.account_id], {
      detached: true,
      stdio: 'ignore',
      cwd: path.join(process.cwd(), '..'),
    });
    
    child.unref();
    
    return NextResponse.json({
      success: true,
      message: `Backfill started for ${wallet.account_id}`,
      walletId,
    });
  } catch (error) {
    console.error('Error starting backfill:', error);
    return NextResponse.json(
      { error: 'Failed to start backfill' },
      { status: 500 }
    );
  }
}

import { NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

export async function GET() {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // Read all indexing jobs for this user, joined with wallet info
    const jobs = await db.all(
      `SELECT ij.id, ij.wallet_id, ij.job_type, ij.chain, ij.status,
              ij.priority, ij.progress_fetched, ij.progress_total,
              ij.last_error, ij.created_at, ij.updated_at, ij.completed_at,
              w.account_id
       FROM indexing_jobs ij
       JOIN wallets w ON ij.wallet_id = w.id
       WHERE ij.user_id = $1
       ORDER BY ij.created_at DESC`,
      [auth.userId]
    );

    // Group jobs by wallet_id
    const byWallet: Record<number, { account_id: string; jobs: typeof jobs }> = {};
    for (const job of jobs) {
      if (!byWallet[job.wallet_id]) {
        byWallet[job.wallet_id] = { account_id: job.account_id, jobs: [] };
      }
      byWallet[job.wallet_id].jobs.push(job);
    }

    // Compute per-wallet aggregated status
    const walletStatuses = Object.entries(byWallet).map(([walletId, data]) => {
      const walletJobs = data.jobs;

      // Determine overall status for this wallet
      const isRunning = walletJobs.some(j => j.status === 'running');
      const isQueued = walletJobs.some(j => j.status === 'queued' || j.status === 'retrying');
      const hasFailed = walletJobs.some(j => j.status === 'failed');
      const allCompleted = walletJobs.every(j => j.status === 'completed');

      let overallStatus: string;
      if (isRunning || isQueued) {
        overallStatus = 'syncing';
      } else if (hasFailed && !isQueued && !isRunning) {
        overallStatus = 'error';
      } else if (allCompleted) {
        overallStatus = 'synced';
      } else {
        overallStatus = 'pending';
      }

      // Compute progress from the full_sync / incremental_sync job
      const txJob = walletJobs.find(j => j.job_type === 'full_sync' || j.job_type === 'incremental_sync');
      const progressFetched = txJob?.progress_fetched ?? 0;
      const progressTotal = txJob?.progress_total ?? 0;

      // Per-job-type breakdown for UI
      const breakdown: Record<string, { status: string; progress_fetched: number; progress_total: number; last_error: string | null }> = {};
      for (const job of walletJobs) {
        // Keep the most recent job per type
        if (!breakdown[job.job_type] || job.created_at > breakdown[job.job_type].created_at) {
          breakdown[job.job_type] = {
            status: job.status,
            progress_fetched: job.progress_fetched ?? 0,
            progress_total: job.progress_total ?? 0,
            last_error: job.last_error ?? null,
          };
        }
      }

      return {
        wallet_id: Number(walletId),
        account_id: data.account_id,
        status: overallStatus,
        progress_fetched: progressFetched,
        progress_total: progressTotal,
        breakdown,
      };
    });

    // Aggregate overall counts
    const totalWallets = walletStatuses.length;
    const synced = walletStatuses.filter(w => w.status === 'synced').length;
    const syncing = walletStatuses.filter(w => w.status === 'syncing').length;
    const error = walletStatuses.filter(w => w.status === 'error').length;
    const pending = walletStatuses.filter(w => w.status === 'pending').length;

    const progress = totalWallets > 0 ? Math.round((synced / totalWallets) * 100) : 0;

    let status: 'idle' | 'syncing' | 'complete' | 'error' = 'idle';
    if (syncing > 0) {
      status = 'syncing';
    } else if (error > 0) {
      status = 'error';
    } else if (synced === totalWallets && totalWallets > 0) {
      status = 'complete';
    }

    // Transaction stats for display
    const walletIds = walletStatuses.map(w => w.wallet_id);
    let txStats = { total: 0, oldest: null as string | null, newest: null as string | null };
    if (walletIds.length > 0) {
      const stats = await db.get<{ total: string; oldest: string | null; newest: string | null }>(
        `SELECT COUNT(*) as total, MIN(block_timestamp) as oldest, MAX(block_timestamp) as newest
         FROM transactions
         WHERE wallet_id = ANY($1::int[])`,
        [walletIds]
      );
      if (stats) {
        txStats = {
          total: Number(stats.total) || 0,
          oldest: stats.oldest,
          newest: stats.newest,
        } as any;
      }
    }

    return NextResponse.json({
      status,
      progress,
      wallets: {
        total: totalWallets.toString(),
        synced: synced.toString(),
        inProgress: syncing.toString(),
        error: error.toString(),
        pending: pending.toString(),
      },
      wallet_details: walletStatuses,
      transactions: {
        total: Number((txStats as any).total) || 0,
        dateRange: txStats.oldest && txStats.newest
          ? { oldest: txStats.oldest, newest: txStats.newest }
          : null,
      },
      lastChecked: new Date().toISOString(),
    });
  } catch (error) {
    console.error('Sync status error:', error);
    return NextResponse.json({ error: 'Failed to get sync status' }, { status: 500 });
  }
}

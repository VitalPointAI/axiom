import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

// Chain display config
const CHAIN_CONFIG: Record<string, { name: string; explorer: string }> = {
  'NEAR': { name: 'NEAR', explorer: 'https://nearblocks.io/address/' },
  'ethereum': { name: 'Ethereum', explorer: 'https://etherscan.io/address/' },
  'polygon': { name: 'Polygon', explorer: 'https://polygonscan.com/address/' },
  'optimism': { name: 'Optimism', explorer: 'https://optimistic.etherscan.io/address/' },
  'cronos': { name: 'Cronos', explorer: 'https://cronoscan.com/address/' },
};

// GET /api/wallets - List user's wallets (NEAR + EVM)
export async function GET() {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // Get NEAR wallets - derive sync_status from indexing_jobs table
    const nearWallets = await db.all(`
      SELECT
        'near-' || w.id as id,
        w.id as raw_id,
        w.account_id as address,
        w.chain,
        w.label,
        COALESCE(
          CASE
            WHEN EXISTS (SELECT 1 FROM indexing_jobs ij WHERE ij.wallet_id = w.id AND ij.status = 'running') THEN 'syncing'
            WHEN EXISTS (SELECT 1 FROM indexing_jobs ij WHERE ij.wallet_id = w.id AND ij.status IN ('queued', 'retrying')) THEN 'pending'
            WHEN EXISTS (SELECT 1 FROM indexing_jobs ij WHERE ij.wallet_id = w.id AND ij.status = 'failed') THEN 'error'
            WHEN EXISTS (SELECT 1 FROM indexing_jobs ij WHERE ij.wallet_id = w.id AND ij.status = 'completed') THEN 'synced'
            ELSE 'pending'
          END
        ) as sync_status,
        (SELECT MAX(ij.completed_at) FROM indexing_jobs ij WHERE ij.wallet_id = w.id AND ij.status = 'completed') as last_synced_at,
        w.created_at,
        COALESCE(
          (SELECT SUM(ij.progress_fetched) FROM indexing_jobs ij WHERE ij.wallet_id = w.id AND ij.job_type = 'full_sync'),
          0
        ) as tx_count,
        'near' as wallet_type
      FROM wallets w
      WHERE w.user_id = $1
      ORDER BY w.created_at DESC
    `, [auth.userId]);

    // Get non-NEAR wallets - wrap in try/catch since EVM tables may not exist yet (Phase 2)
    let evmWallets: any[] = [];
    try {
      evmWallets = await db.all(`
        SELECT
          'evm-' || w.id as id,
          w.id as raw_id,
          w.account_id as address,
          w.chain,
          COALESCE(w.label, w.account_id) as label,
          'pending' as sync_status,
          NULL as last_synced_at,
          w.created_at,
          0 as tx_count,
          'evm' as wallet_type
        FROM wallets w
        WHERE w.user_id = $1 AND w.chain != 'near' AND w.chain != 'NEAR'
        ORDER BY w.created_at DESC
      `, [auth.userId]);
    } catch {
      // EVM wallets query may fail if chain filter returns no results or table issues (Phase 2)
    }

    // Add chain display names and explorer URLs
    const formatWallet = (w: any) => ({
      ...w,
      chain_name: CHAIN_CONFIG[w.chain]?.name || w.chain,
      explorer_url: CHAIN_CONFIG[w.chain]?.explorer
        ? CHAIN_CONFIG[w.chain].explorer + w.address
        : null,
    });

    const wallets = [
      ...nearWallets.map(formatWallet),
      ...evmWallets.map(formatWallet),
    ];

    return NextResponse.json({ wallets });
  } catch (error) {
    console.error('Wallets fetch error:', error);
    return NextResponse.json({ error: 'Failed to fetch wallets' }, { status: 500 });
  }
}

// POST /api/wallets - Add a new wallet
export async function POST(request: NextRequest) {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { address, chain, label } = await request.json();

    if (!address || !chain) {
      return NextResponse.json({ error: 'Address and chain are required' }, { status: 400 });
    }

    const normalizedChain = chain.toLowerCase();
    const isEVM = ['ethereum', 'polygon', 'optimism', 'arbitrum', 'base', 'eth', 'cronos'].includes(normalizedChain);

    // Validate address format
    if (chain === 'NEAR' || chain === 'near') {
      if (!address.endsWith('.near') && !address.match(/^[a-f0-9]{64}$/)) {
        return NextResponse.json({ error: 'Invalid NEAR address format' }, { status: 400 });
      }
    } else if (isEVM) {
      if (!address.match(/^0x[a-fA-F0-9]{40}$/i)) {
        return NextResponse.json({ error: 'Invalid EVM address format' }, { status: 400 });
      }
    }

    if (isEVM) {
      // Handle EVM wallet - stored in unified wallets table with chain column
      const evmChain = normalizedChain === 'eth' ? 'ethereum' : normalizedChain;
      const normalizedAddr = address.toLowerCase();

      // Check for duplicate FOR THIS USER
      const existing = await db.get(
        `SELECT id FROM wallets WHERE account_id = $1 AND chain = $2 AND user_id = $3`,
        [normalizedAddr, evmChain, auth.userId]
      );

      if (existing) {
        return NextResponse.json({ error: 'Wallet already exists' }, { status: 409 });
      }

      // Insert EVM wallet into unified wallets table
      const result = await db.run(
        `INSERT INTO wallets (account_id, chain, label, is_owned, user_id)
         VALUES ($1, $2, $3, TRUE, $4)`,
        [normalizedAddr, evmChain, label || `${evmChain} Wallet`, auth.userId]
      );

      const wallet = await db.get(`
        SELECT
          'evm-' || id as id,
          id as raw_id,
          account_id as address,
          chain,
          label,
          'pending' as sync_status,
          NULL as last_synced_at,
          created_at,
          0 as tx_count,
          'evm' as wallet_type
        FROM wallets WHERE id = $1
      `, [result.lastInsertRowid]) as any;

      // EVM indexing job queue integration is pending (Phase 2 scope).
      // Wallet is recorded; indexing will be triggered via job queue once EVM handlers are registered.

      return NextResponse.json({
        wallet: {
          ...wallet,
          chain_name: CHAIN_CONFIG[evmChain]?.name || evmChain,
          explorer_url: CHAIN_CONFIG[evmChain]?.explorer + normalizedAddr,
        }
      }, { status: 201 });

    } else {
      // Handle NEAR wallet
      const existing = await db.get(
        `SELECT id, user_id FROM wallets WHERE account_id = $1`,
        [address]
      ) as any;

      if (existing) {
        // If wallet exists with no user, claim it
        if (!existing.user_id) {
          await db.run(`UPDATE wallets SET user_id = $1 WHERE id = $2`, [auth.userId, existing.id]);
          const updated = await db.get(`SELECT * FROM wallets WHERE id = $1`, [existing.id]);
          return NextResponse.json({ wallet: updated }, { status: 200 });
        }

        // If wallet exists for this user, return it
        if (existing.user_id === auth.userId) {
          const wallet = await db.get(`SELECT * FROM wallets WHERE id = $1`, [existing.id]);
          return NextResponse.json({ wallet }, { status: 200 });
        }

        // Wallet belongs to another user
        return NextResponse.json({ error: 'Wallet already exists for another user' }, { status: 409 });
      }

      // Insert NEAR wallet - no sync_status column in wallets table (derived from indexing_jobs)
      const result = await db.run(
        `INSERT INTO wallets (account_id, chain, label, user_id)
         VALUES ($1, 'NEAR', $2, $3)`,
        [address, label || address.slice(0, 16) + '...', auth.userId]
      );

      const wallet = await db.get(`
        SELECT
          'near-' || id as id,
          id as raw_id,
          account_id as address,
          chain,
          label,
          'pending' as sync_status,
          NULL as last_synced_at,
          created_at,
          0 as tx_count,
          'near' as wallet_type
        FROM wallets WHERE id = $1
      `, [result.lastInsertRowid]) as any;

      // Create background indexing jobs (queued, not immediate — decoupled via job queue)
      const walletId = wallet.raw_id;
      const userId = auth.userId;

      try {
        // Job 1: Full transaction history sync
        await db.run(
          `INSERT INTO indexing_jobs (user_id, wallet_id, job_type, chain, status, priority)
           VALUES ($1, $2, 'full_sync', 'near', 'queued', 10)`,
          [userId, walletId]
        );

        // Job 2: Staking rewards sync
        await db.run(
          `INSERT INTO indexing_jobs (user_id, wallet_id, job_type, chain, status, priority)
           VALUES ($1, $2, 'staking_sync', 'near', 'queued', 5)`,
          [userId, walletId]
        );

        // Job 3: Lockup contract sync (NEAR chain only)
        await db.run(
          `INSERT INTO indexing_jobs (user_id, wallet_id, job_type, chain, status, priority)
           VALUES ($1, $2, 'lockup_sync', 'near', 'queued', 3)`,
          [userId, walletId]
        );

        wallet.sync_status = 'queued';
      } catch (err) {
        console.error('Failed to create indexing jobs:', err);
        // Jobs are best-effort — wallet is still created successfully
      }

      return NextResponse.json({
        wallet: {
          ...wallet,
          chain_name: 'NEAR',
          explorer_url: 'https://nearblocks.io/address/' + address,
          sync_status: 'queued',
        }
      }, { status: 201 });
    }
  } catch (error) {
    console.error('Wallet create error:', error);
    return NextResponse.json({ error: 'Failed to create wallet' }, { status: 500 });
  }
}

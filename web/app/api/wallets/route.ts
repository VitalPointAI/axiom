import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
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

    const db = getDb();

    // Get NEAR wallets - FILTERED BY USER_ID
    const nearWallets = await db.prepare(`
      SELECT 
        'near-' || w.id as id,
        w.id as raw_id,
        w.account_id as address,
        w.chain,
        w.label,
        COALESCE(w.sync_status, p.status, 'pending') as sync_status,
        NULL as last_synced_at,
        w.created_at,
        COALESCE(p.total_fetched, 0) as tx_count,
        'near' as wallet_type
      FROM wallets w
      LEFT JOIN indexing_progress p ON w.id = p.wallet_id
      WHERE w.user_id = $1
      ORDER BY w.created_at DESC
    `).all(auth.userId) as any[];

    // Get EVM wallets - FILTERED BY USER_ID (SECURITY FIX)
    const evmWallets = await db.prepare(`
      SELECT 
        'evm-' || ew.id as id,
        ew.id as raw_id,
        ew.address,
        ew.chain,
        COALESCE(ew.label, ew.address) as label,
        COALESCE(ep.status, 'complete') as sync_status,
        ep.updated_at as last_synced_at,
        ew.created_at,
        COALESCE(ep.total_fetched, 0) as tx_count,
        'evm' as wallet_type
      FROM evm_wallets ew
      LEFT JOIN evm_indexing_progress ep ON ew.id = ep.wallet_id
      WHERE ew.user_id = $1 AND ew.is_owned = TRUE
      ORDER BY ew.created_at DESC
    `).all(auth.userId) as any[];

    // Get XRP wallets - FILTERED BY USER_ID
    const xrpWallets = await db.prepare(`
      SELECT 
        'xrp-' || w.id as id,
        w.id as raw_id,
        w.address,
        'xrp' as chain,
        COALESCE(w.label, w.address) as label,
        'complete' as sync_status,
        NULL as last_synced_at,
        w.created_at,
        0 as tx_count,
        'xrp' as wallet_type
      FROM xrp_wallets w
      WHERE w.user_id = $1
      ORDER BY w.created_at DESC
    `).all(auth.userId) as any[];

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
      ...xrpWallets.map(formatWallet),
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

    const db = getDb();
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
      // Handle EVM wallet
      const evmChain = normalizedChain === 'eth' ? 'ethereum' : normalizedChain;
      const normalizedAddr = address.toLowerCase();

      // Check for duplicate FOR THIS USER
      const existing = await db.prepare(`
        SELECT id FROM evm_wallets WHERE address = $1 AND chain = $2 AND user_id = $3
      `).get(normalizedAddr, evmChain, auth.userId);

      if (existing) {
        return NextResponse.json({ error: 'Wallet already exists' }, { status: 409 });
      }

      // Insert EVM wallet WITH user_id (SECURITY FIX)
      const result = await db.prepare(`
        INSERT INTO evm_wallets (address, chain, label, is_owned, user_id)
        VALUES ($1, $2, $3, TRUE, $4)
      `).run(normalizedAddr, evmChain, label || `${evmChain} Wallet`, auth.userId);

      const wallet = await db.prepare(`
        SELECT 
          'evm-' || id as id,
          id as raw_id,
          address,
          chain,
          label,
          'pending' as sync_status,
          created_at,
          0 as tx_count,
          'evm' as wallet_type
        FROM evm_wallets WHERE id = $1
      `).get(result.lastInsertRowid) as any;

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
      // Handle NEAR wallet (existing logic)
      const existing = await db.prepare(`SELECT id, user_id FROM wallets WHERE account_id = $1`).get(address) as any;

      if (existing) {
        // If wallet exists with no user, claim it
        if (!existing.user_id) {
          await db.prepare(`UPDATE wallets SET user_id = $1 WHERE id = $2`).run(auth.userId, existing.id);
          const updated = await db.prepare(`SELECT * FROM wallets WHERE id = $1`).get(existing.id);
          return NextResponse.json({ wallet: updated }, { status: 200 });
        }
        
        // If wallet exists for this user, return it
        if (existing.user_id === auth.userId) {
          const wallet = await db.prepare(`SELECT * FROM wallets WHERE id = $1`).get(existing.id);
          return NextResponse.json({ wallet }, { status: 200 });
        }
        
        // Wallet belongs to another user
        return NextResponse.json({ error: 'Wallet already exists for another user' }, { status: 409 });
      }

      // Insert NEAR wallet
      const result = await db.prepare(`
        INSERT INTO wallets (account_id, chain, label, user_id, sync_status)
        VALUES ($1, 'NEAR', $2, $3, 'pending')
      `).run(address, label || address.slice(0, 16) + '...', auth.userId);

      const wallet = await db.prepare(`
        SELECT 
          'near-' || id as id,
          id as raw_id,
          account_id as address, 
          chain, 
          label, 
          sync_status, 
          last_synced_at, 
          created_at,
          0 as tx_count,
          'near' as wallet_type
        FROM wallets WHERE id = $1
      `).get(result.lastInsertRowid) as any;

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

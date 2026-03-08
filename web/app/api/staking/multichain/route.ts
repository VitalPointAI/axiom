import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { getAuthenticatedUser } from "@/lib/auth";

/**
 * Multi-chain staking API
 * Returns staking positions across all supported chains (Akash, XRP, Crypto.org, etc.)
 * SECURITY: All queries filtered by user_id
 */

interface StakingPosition {
  chain: string;
  chainSymbol: string;
  address: string;
  label: string;
  stakedAmount: number;
  pendingRewards: number;
  validators: string[];
  totalValue: number;
  lastUpdated: string;
}

export async function GET(request: NextRequest) {
  try {
    const user = await getAuthenticatedUser();
    if (!user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const db = getDb();
    const positions: StakingPosition[] = [];

    // Fetch Akash staking - FILTERED BY USER_ID (SECURITY FIX)
    const akashWallets = await db.prepare(`
      SELECT address, label, staked_amount, staking_rewards, validators, created_at
      FROM akash_wallets 
      WHERE user_id = $1 AND is_owned = TRUE AND (staked_amount > 0 OR staking_rewards > 0)
    `).all(user.userId) as any[];

    for (const w of akashWallets) {
      positions.push({
        chain: 'Akash',
        chainSymbol: 'AKT',
        address: w.address,
        label: w.label || 'Akash Wallet',
        stakedAmount: Number(w.staked_amount) || 0,
        pendingRewards: Number(w.staking_rewards) || 0,
        validators: w.validators ? w.validators.split(',') : [],
        totalValue: (Number(w.staked_amount) || 0) + (Number(w.staking_rewards) || 0),
        lastUpdated: w.created_at,
      });
    }

    // Fetch Crypto.org staking - FILTERED BY USER_ID (SECURITY FIX)
    try {
      const croWallets = await db.prepare(`
        SELECT address, label, staked_amount, staking_rewards, validators, created_at
        FROM cryptoorg_wallets 
        WHERE user_id = $1 AND is_owned = TRUE AND (staked_amount > 0 OR staking_rewards > 0)
      `).all(user.userId) as any[];

      for (const w of croWallets) {
        positions.push({
          chain: 'Crypto.org',
          chainSymbol: 'CRO',
          address: w.address,
          label: w.label || 'CRO Wallet',
          stakedAmount: Number(w.staked_amount) || 0,
          pendingRewards: Number(w.staking_rewards) || 0,
          validators: w.validators ? w.validators.split(',') : [],
          totalValue: (Number(w.staked_amount) || 0) + (Number(w.staking_rewards) || 0),
          lastUpdated: w.created_at,
        });
      }
    } catch (e) {
      // Table might not exist yet
    }

    // Calculate totals
    const totals = {
      totalStaked: positions.reduce((sum, p) => sum + p.stakedAmount, 0),
      totalPendingRewards: positions.reduce((sum, p) => sum + p.pendingRewards, 0),
      totalValue: positions.reduce((sum, p) => sum + p.totalValue, 0),
      chainCount: new Set(positions.map(p => p.chain)).size,
    };

    return NextResponse.json({
      positions,
      totals,
    });
  } catch (error: any) {
    console.error("Multi-chain staking error:", error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

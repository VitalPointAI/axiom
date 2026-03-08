import { NextResponse } from 'next/server';
import { getAuthenticatedUser } from '@/lib/auth';
import { Pool } from 'pg';

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 'postgresql://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax'
});

// Token decimals for manual conversion when amount_decimal is null
const TOKEN_DECIMALS: Record<string, number> = {
  'wrap.near': 24,
  'wNEAR': 24,
  'rNEAR': 24,
  'lst.rhealab.near': 24,
  'STNEAR': 24,
  'meta-pool.near': 24,
  'ETH': 18,
  'DAI': 18,
  'USDC': 6,
  'USDC.e': 6,
  'USDT.e': 6,
  'ZEC': 8,
  'xRHEA': 18,
  'XRHEA': 18,
};

function getDecimals(token: string, contract?: string): number {
  if (contract && TOKEN_DECIMALS[contract]) return TOKEN_DECIMALS[contract];
  if (TOKEN_DECIMALS[token]) return TOKEN_DECIMALS[token];
  return 18; // Default for most tokens
}

// Format numbers for display
function formatFiat(value: number): string {
  return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatCrypto(value: number): string {
  return value.toLocaleString('en-US', { minimumFractionDigits: 5, maximumFractionDigits: 5 });
}

// Get Ref Finance prices for valuation
async function getRefPrices(): Promise<Record<string, number>> {
  try {
    const resp = await fetch('https://api.ref.finance/list-token-price', {
      next: { revalidate: 60 }
    });
    if (!resp.ok) return {};
    const data = await resp.json();
    
    const prices: Record<string, number> = {};
    for (const [contractId, info] of Object.entries(data)) {
      const price = parseFloat((info as any)?.price || '0');
      const symbol = (info as any)?.symbol;
      if (price > 0) {
        prices[contractId] = price;
        if (symbol) {
          prices[symbol] = price;
          prices[symbol.toUpperCase()] = price;
        }
      }
    }
    return prices;
  } catch {
    return {};
  }
}

export async function GET() {
  try {
    const auth = await getAuthenticatedUser();
    if (!auth) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

    const client = await pool.connect();
    
    try {
      // Get current DeFi positions - aggregate by token across all wallets
      // Normalize token_symbol to UPPER for grouping to avoid case duplicates
      const positionsResult = await client.query(`
        SELECT 
          de.protocol,
          de.event_type,
          UPPER(de.token_symbol) as token_symbol,
          SUM(de.amount_decimal) as amount_decimal,
          MAX(de.block_timestamp) as block_timestamp,
          COUNT(DISTINCT w.account_id) as wallet_count,
          STRING_AGG(DISTINCT w.account_id, ', ') as wallets
        FROM defi_events de
        JOIN wallets w ON de.wallet_id = w.id
        WHERE w.user_id = $1
          AND de.event_type IN ('supply', 'collateral', 'borrow', 'stake', 'farm', 'lp')
          AND de.amount_decimal > 0
        GROUP BY de.protocol, de.event_type, UPPER(de.token_symbol)
        ORDER BY de.event_type, token_symbol
      `, [auth.userId]);

      // Get prices
      const prices = await getRefPrices();

      // Group by position type
      const supplied: any[] = [];
      const collateral: any[] = [];
      const borrowed: any[] = [];
      const staking: any[] = [];
      const farming: any[] = [];
      const liquidity: any[] = [];

      let totalSuppliedUsd = 0;
      let totalCollateralUsd = 0;
      let totalBorrowedUsd = 0;
      let totalStakingUsd = 0;
      let totalFarmingUsd = 0;
      let totalLiquidityUsd = 0;

      for (const pos of positionsResult.rows) {
        // Use aggregated amount_decimal from SQL SUM
        const amount = parseFloat(pos.amount_decimal) || 0;

        if (amount < 0.00001) continue; // Skip dust

        // Look up price - token_symbol is already uppercase from SQL
        const price = prices[pos.token_symbol] || prices[pos.token_symbol?.toLowerCase()] || 0;
        const valueUsd = amount * price;

        const position = {
          protocol: pos.protocol,
          token: pos.token_symbol,
          amount,
          amountFormatted: formatCrypto(amount),
          price,
          priceFormatted: formatFiat(price),
          valueUsd,
          valueUsdFormatted: formatFiat(valueUsd),
          walletCount: parseInt(pos.wallet_count) || 1,
          wallets: pos.wallets
        };

        switch (pos.event_type) {
          case 'supply':
            supplied.push(position);
            totalSuppliedUsd += valueUsd;
            break;
          case 'collateral':
            collateral.push(position);
            totalCollateralUsd += valueUsd;
            break;
          case 'borrow':
            borrowed.push(position);
            totalBorrowedUsd += valueUsd;
            break;
          case 'stake':
            staking.push(position);
            totalStakingUsd += valueUsd;
            break;
          case 'farm':
            farming.push(position);
            totalFarmingUsd += valueUsd;
            break;
          case 'lp':
            liquidity.push(position);
            totalLiquidityUsd += valueUsd;
            break;
        }
      }

      // Net DeFi value = supplied + collateral + staking + farming + LP - borrowed
      const netDefiValue = totalSuppliedUsd + totalCollateralUsd + totalStakingUsd + totalFarmingUsd + totalLiquidityUsd - totalBorrowedUsd;

      return NextResponse.json({
        positions: {
          supplied,
          collateral,
          borrowed,
          staking,
          farming,
          liquidity
        },
        totals: {
          supplied: totalSuppliedUsd,
          suppliedFormatted: formatFiat(totalSuppliedUsd),
          collateral: totalCollateralUsd,
          collateralFormatted: formatFiat(totalCollateralUsd),
          borrowed: totalBorrowedUsd,
          borrowedFormatted: formatFiat(totalBorrowedUsd),
          staking: totalStakingUsd,
          stakingFormatted: formatFiat(totalStakingUsd),
          farming: totalFarmingUsd,
          farmingFormatted: formatFiat(totalFarmingUsd),
          liquidity: totalLiquidityUsd,
          liquidityFormatted: formatFiat(totalLiquidityUsd),
          netValue: netDefiValue,
          netValueFormatted: formatFiat(netDefiValue)
        }
      });
    } finally {
      client.release();
    }
  } catch (error) {
    console.error('DeFi positions error:', error);
    return NextResponse.json({ error: 'Failed to fetch positions' }, { status: 500 });
  }
}

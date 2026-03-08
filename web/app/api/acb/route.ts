import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const year = searchParams.get("year") || "2025";
  
  const db = getDb();
  
  // Get calculated disposals for the year
  const disposalsStmt = await db.prepare(`
    SELECT token, disposal_date, amount, proceeds_cad, acb_cad,
           gain_loss_cad, taxable_gain, allowable_loss
    FROM calculated_disposals
    WHERE year = ?
    ORDER BY disposal_date
  `);
  const disposals = await disposalsStmt.all(parseInt(year));
  
  // Calculate totals
  let totalProceeds = 0, totalAcb = 0, totalGainLoss = 0;
  let totalTaxableGain = 0, totalAllowableLoss = 0;
  
  for (const d of disposals as any[]) {
    totalProceeds += d.proceeds_cad || 0;
    totalAcb += d.acb_cad || 0;
    totalGainLoss += d.gain_loss_cad || 0;
    totalTaxableGain += d.taxable_gain || 0;
    totalAllowableLoss += d.allowable_loss || 0;
  }
  
  // NEAR holdings - exclude non-taxable categories
  const nearHoldingsStmt = await db.prepare(`
    SELECT 
      SUM(CASE WHEN direction = 'in' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as total_in,
      SUM(CASE WHEN direction = 'out' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as total_out,
      SUM(CASE WHEN direction = 'in' THEN COALESCE(cost_basis_cad, 0) ELSE 0 END) as total_cost
    FROM transactions
    WHERE amount IS NOT NULL 
    AND CAST(amount AS REAL) > 0
    AND (tax_category IS NULL OR tax_category NOT IN 
      ('unstake_return', 'internal', 'staking_deposit', 'fee_only', 
       'unknown', 'contract_deploy', 'account_create', 'nft_purchase'))
  `);
  const nearHoldings = await nearHoldingsStmt.get() as { total_in: number; total_out: number; total_cost: number };
  
  const nearBalance = (nearHoldings?.total_in || 0) - (nearHoldings?.total_out || 0);
  const nearAcb = nearHoldings?.total_cost || 0;
  
  // FT holdings
  const ftHoldingsStmt = await db.prepare(`
    SELECT 
      token_symbol,
      SUM(CASE WHEN direction = 'in' THEN CAST(amount AS REAL) / POWER(10, COALESCE(token_decimals, 24)) ELSE 0 END) -
      SUM(CASE WHEN direction = 'out' THEN CAST(amount AS REAL) / POWER(10, COALESCE(token_decimals, 24)) ELSE 0 END) as balance,
      SUM(CASE WHEN direction = 'in' THEN COALESCE(value_cad, 0) ELSE 0 END) as cost_cad
    FROM ft_transactions
    WHERE token_symbol IS NOT NULL
    GROUP BY token_symbol
    HAVING balance > 0.01
    ORDER BY cost_cad DESC
    LIMIT 20
  `);
  const ftHoldings = await ftHoldingsStmt.all() as { token_symbol: string; balance: number; cost_cad: number }[];
  
  // Pricing status
  const statusStmt = await db.prepare(`
    SELECT 
      SUM(CASE WHEN cost_basis_cad > 0 THEN 1 ELSE 0 END) as priced,
      SUM(CASE WHEN cost_basis_cad IS NULL OR cost_basis_cad = 0 THEN 1 ELSE 0 END) as unpriced,
      COUNT(*) as total
    FROM transactions
    WHERE amount IS NOT NULL AND CAST(amount AS REAL) > 0
  `);
  const status = await statusStmt.get() as { priced: number; unpriced: number; total: number };

  return NextResponse.json({
    year,
    summary: {
      disposalCount: disposals.length,
      totalProceeds,
      totalAcb,
      netGainLoss: totalGainLoss,
      taxableCapitalGain: totalTaxableGain,
      allowableCapitalLoss: totalAllowableLoss,
      line12700: totalTaxableGain
    },
    holdings: {
      near: {
        units: nearBalance,
        acb: nearAcb,
        acbPerUnit: nearBalance > 0 ? nearAcb / nearBalance : 0
      },
      tokens: ftHoldings.map(t => ({
        symbol: t.token_symbol,
        balance: t.balance,
        costCad: t.cost_cad
      }))
    },
    pricingStatus: {
      priced: status?.priced || 0,
      unpriced: status?.unpriced || 0,
      total: status?.total || 0,
      percentComplete: status?.total > 0 ? Math.round((status.priced / status.total) * 100) : 0
    },
    disposals: (disposals as any[]).slice(0, 50),
    hasMore: disposals.length > 50
  });
}

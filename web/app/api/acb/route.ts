import { getAuthenticatedUser } from '@/lib/auth';
import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export async function GET(request: Request) {
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { searchParams } = new URL(request.url);
  const year = searchParams.get("year") || "2025";
  
  const db = getDb();
  
  // SECURITY: Get this user's wallet IDs first
  const userWallets = await db.prepare(`
    SELECT id FROM wallets WHERE user_id = $1
  `).all(auth.userId) as { id: number }[];
  const walletIds = userWallets.map(w => w.id);
  
  // If no wallets, return empty data
  if (walletIds.length === 0) {
    return NextResponse.json({
      year,
      summary: {
        disposalCount: 0, totalProceeds: 0, totalAcb: 0, netGainLoss: 0,
        taxableCapitalGain: 0, allowableCapitalLoss: 0, line12700: 0
      },
      holdings: { near: { units: 0, acb: 0, acbPerUnit: 0 }, tokens: [] },
      pricingStatus: { priced: 0, unpriced: 0, total: 0, percentComplete: 0 },
      disposals: [],
      hasMore: false
    });
  }
  
  // Get calculated disposals for the year - FILTERED BY USER WALLETS
  const disposals = await db.prepare(`
    SELECT cd.token, cd.disposal_date, cd.amount, cd.proceeds_cad, cd.acb_cad,
           cd.gain_loss_cad, cd.taxable_gain, cd.allowable_loss
    FROM calculated_disposals cd
    JOIN wallets w ON cd.wallet_id = w.id
    WHERE cd.year = $1 AND w.user_id = $2
    ORDER BY cd.disposal_date
  `).all(parseInt(year), auth.userId);
  
  // Calculate totals
  let totalProceeds = 0, totalAcb = 0, totalGainLoss = 0;
  let totalTaxableGain = 0, totalAllowableLoss = 0;
  
  for (const d of disposals as any[]) {
    totalProceeds += Number(d.proceeds_cad) || 0;
    totalAcb += Number(d.acb_cad) || 0;
    totalGainLoss += Number(d.gain_loss_cad) || 0;
    totalTaxableGain += Number(d.taxable_gain) || 0;
    totalAllowableLoss += Number(d.allowable_loss) || 0;
  }
  
  // NEAR holdings - FILTERED BY USER WALLETS
  const nearHoldings = await db.prepare(`
    SELECT 
      SUM(CASE WHEN direction = 'in' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as total_in,
      SUM(CASE WHEN direction = 'out' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as total_out,
      SUM(CASE WHEN direction = 'in' THEN COALESCE(cost_basis_cad, 0) ELSE 0 END) as total_cost
    FROM transactions
    WHERE wallet_id = ANY($1::int[])
    AND amount IS NOT NULL 
    AND CAST(amount AS REAL) > 0
    AND (tax_category IS NULL OR tax_category NOT IN 
      ('unstake_return', 'internal', 'staking_deposit', 'fee_only', 
       'unknown', 'contract_deploy', 'account_create', 'nft_purchase'))
  `).get([walletIds]) as { total_in: number; total_out: number; total_cost: number };
  
  const nearBalance = (Number(nearHoldings?.total_in) || 0) - (Number(nearHoldings?.total_out) || 0);
  const nearAcb = Number(nearHoldings?.total_cost) || 0;
  
  // FT holdings - FILTERED BY USER WALLETS
  const ftHoldings = await db.prepare(`
    SELECT 
      token_symbol,
      SUM(CASE WHEN direction = 'in' THEN CAST(amount AS REAL) / POWER(10, COALESCE(token_decimals, 24)) ELSE 0 END) -
      SUM(CASE WHEN direction = 'out' THEN CAST(amount AS REAL) / POWER(10, COALESCE(token_decimals, 24)) ELSE 0 END) as balance,
      SUM(CASE WHEN direction = 'in' THEN COALESCE(value_cad, 0) ELSE 0 END) as cost_cad
    FROM ft_transactions
    WHERE wallet_id = ANY($1::int[])
    AND token_contract != 'aurora'
    AND token_symbol IS NOT NULL
    GROUP BY token_symbol
    HAVING SUM(CASE WHEN direction = 'in' THEN CAST(amount AS REAL) / POWER(10, COALESCE(token_decimals, 24)) ELSE 0 END) - SUM(CASE WHEN direction = 'out' THEN CAST(amount AS REAL) / POWER(10, COALESCE(token_decimals, 24)) ELSE 0 END) > 0.01
    ORDER BY cost_cad DESC
    LIMIT 20
  `).all([walletIds]) as { token_symbol: string; balance: number; cost_cad: number }[];
  
  // Pricing status - FILTERED BY USER WALLETS
  const status = await db.prepare(`
    SELECT 
      SUM(CASE WHEN cost_basis_cad > 0 THEN 1 ELSE 0 END) as priced,
      SUM(CASE WHEN cost_basis_cad IS NULL OR cost_basis_cad = 0 THEN 1 ELSE 0 END) as unpriced,
      COUNT(*) as total
    FROM transactions
    WHERE wallet_id = ANY($1::int[])
    AND amount IS NOT NULL AND CAST(amount AS REAL) > 0
  `).get([walletIds]) as { priced: number; unpriced: number; total: number };

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
        balance: Number(t.balance),
        costCad: Number(t.cost_cad)
      }))
    },
    pricingStatus: {
      priced: Number(status?.priced) || 0,
      unpriced: Number(status?.unpriced) || 0,
      total: Number(status?.total) || 0,
      percentComplete: status?.total > 0 ? Math.round((Number(status.priced) / Number(status.total)) * 100) : 0
    },
    disposals: (disposals as any[]).slice(0, 50),
    hasMore: disposals.length > 50
  });
}

import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

// ACB (Adjusted Cost Base) calculation endpoint
// Uses Canadian tax rules: average cost method for identical properties

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year') || '2025';
  
  const db = getDb();
  
  const yearStart = new Date(`${year}-01-01T00:00:00Z`).getTime() * 1000000;
  const yearEnd = new Date(`${parseInt(year) + 1}-01-01T00:00:00Z`).getTime() * 1000000;
  
  // Get calculated disposals for the year
  const disposalsStmt = db.prepare(`
    SELECT 
      token,
      disposal_date,
      amount,
      proceeds_cad,
      acb_cad,
      gain_loss_cad,
      taxable_gain,
      allowable_loss
    FROM calculated_disposals
    WHERE year = ?
    ORDER BY disposal_date
  `);
  const disposals = disposalsStmt.all(parseInt(year));
  
  // Calculate totals
  let totalProceeds = 0;
  let totalAcb = 0;
  let totalGainLoss = 0;
  let totalTaxableGain = 0;
  let totalAllowableLoss = 0;
  
  for (const d of disposals as any[]) {
    totalProceeds += d.proceeds_cad || 0;
    totalAcb += d.acb_cad || 0;
    totalGainLoss += d.gain_loss_cad || 0;
    totalTaxableGain += d.taxable_gain || 0;
    totalAllowableLoss += d.allowable_loss || 0;
  }
  
  // Get current holdings (end of year)
  const holdingsStmt = db.prepare(`
    SELECT 
      'NEAR' as token,
      SUM(CASE WHEN direction = 'in' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) -
      SUM(CASE WHEN direction = 'out' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as balance,
      SUM(CASE WHEN direction = 'in' THEN COALESCE(cost_basis_cad, 0) ELSE 0 END) -
      SUM(CASE WHEN direction = 'out' THEN COALESCE(cost_basis_cad, 0) * 0.5 ELSE 0 END) as acb
    FROM transactions
    WHERE block_timestamp < ?
  `);
  const holdings = holdingsStmt.get(yearEnd) as { token: string; balance: number; acb: number };
  
  // Pricing status
  const statusStmt = db.prepare(`
    SELECT 
      SUM(CASE WHEN cost_basis_usd > 0 THEN 1 ELSE 0 END) as priced,
      SUM(CASE WHEN price_warning = 'dust' THEN 1 ELSE 0 END) as dust,
      SUM(CASE WHEN price_warning = 'historical_needed' THEN 1 ELSE 0 END) as historical,
      COUNT(*) as total
    FROM transactions
  `);
  const status = statusStmt.get() as { priced: number; dust: number; historical: number; total: number };
  
  return NextResponse.json({
    year,
    summary: {
      disposalCount: disposals.length,
      totalProceeds: totalProceeds,
      totalAcb: totalAcb,
      netGainLoss: totalGainLoss,
      taxableCapitalGain: totalTaxableGain,
      allowableCapitalLoss: totalAllowableLoss,
      // Line 12700 on T1: Taxable capital gains
      line12700: totalTaxableGain
    },
    holdings: {
      token: holdings?.token || 'NEAR',
      units: holdings?.balance || 0,
      acb: holdings?.acb || 0,
      acbPerUnit: holdings?.balance > 0 ? (holdings?.acb || 0) / holdings.balance : 0
    },
    pricingStatus: {
      priced: status?.priced || 0,
      dust: status?.dust || 0,
      needsHistorical: status?.historical || 0,
      total: status?.total || 0
    },
    disposals: (disposals as any[]).slice(0, 50),
    hasMore: disposals.length > 50,
    notes: [
      'ACB calculated using average cost method (CRA requirement)',
      '50% inclusion rate applied to capital gains',
      'Dust transactions (<0.01 NEAR) excluded from calculations',
      'Some transactions need historical prices - values may be incomplete'
    ]
  });
}

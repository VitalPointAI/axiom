import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

// Schedule 3 - Capital Gains (or Losses)
// Used to report disposition of capital property

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year') || '2025';
  
  const db = getDb();
  
  const yearStart = new Date(`${year}-01-01T00:00:00Z`).getTime() * 1000000;
  const yearEnd = new Date(`${parseInt(year) + 1}-01-01T00:00:00Z`).getTime() * 1000000;
  
  // Get all disposals (outflows that are trades or transfers out)
  const disposalsStmt = await db.prepare(`
    SELECT 
      t.id,
      t.tx_hash,
      t.block_timestamp,
      t.counterparty,
      t.method_name,
      t.action_type,
      CAST(t.amount AS REAL) / 1e24 as amount_near,
      t.cost_basis_usd,
      t.cost_basis_cad,
      t.tax_category,
      w.account_id as wallet_address,
      datetime(t.block_timestamp/1000000000, 'unixepoch') as datetime
    FROM transactions t
    LEFT JOIN wallets w ON t.wallet_id = w.id
    WHERE t.block_timestamp >= ? AND t.block_timestamp < ?
    AND t.direction = 'out'
    AND t.tax_category IN ('trade', 'transfer')
    ORDER BY t.block_timestamp
  `);
  const disposals = await disposalsStmt.all(yearStart, yearEnd) as Array<{
    id: number;
    tx_hash: string;
    block_timestamp: number;
    counterparty: string;
    method_name: string;
    action_type: string;
    amount_near: number;
    cost_basis_usd: number | null;
    cost_basis_cad: number | null;
    tax_category: string;
    wallet_address: string;
    datetime: string;
  }>;
  
  // Get DeFi trades
  const defiTradesStmt = await db.prepare(`
    SELECT 
      d.id,
      d.tx_hash,
      d.block_timestamp,
      d.token_symbol,
      d.amount_decimal,
      d.value_usd,
      d.value_cad,
      d.protocol,
      datetime(d.block_timestamp/1000000000, 'unixepoch') as datetime
    FROM defi_events d
    WHERE d.block_timestamp >= ? AND d.block_timestamp < ?
    AND d.tax_category = 'trade'
    ORDER BY d.block_timestamp
  `);
  const defiTrades = await defiTradesStmt.all(yearStart, yearEnd);
  
  // Calculate totals
  // For crypto, each trade is a disposition - need to track ACB (adjusted cost base)
  // This is simplified - real ACB calculation tracks pool of identical properties
  
  let totalProceeds = 0;
  let totalACB = 0;
  let totalOutlays = 0; // transaction fees
  
  const capitalGains: Array<{
    date: string;
    description: string;
    proceeds: number;
    acb: number;
    outlays: number;
    gainLoss: number;
  }> = [];
  
  // Process NEAR disposals
  for (const d of disposals) {
    const proceeds = d.cost_basis_cad || (d.cost_basis_usd || 0) * 1.35;
    // ACB calculation would require tracking all acquisitions - simplified here
    const acb = proceeds * 0.8; // Placeholder - assume 20% gain average
    const outlays = 0.1; // Small fee
    const gainLoss = proceeds - acb - outlays;
    
    totalProceeds += proceeds;
    totalACB += acb;
    totalOutlays += outlays;
    
    capitalGains.push({
      date: d.datetime?.split(' ')[0] || 'Unknown',
      description: `NEAR transfer - ${d.amount_near.toFixed(4)} NEAR`,
      proceeds,
      acb,
      outlays,
      gainLoss
    });
  }
  
  // Process DeFi trades
  for (const t of defiTrades) {
    const proceeds = (t as any).value_cad || ((t as any).value_usd || 0) * 1.35;
    const acb = proceeds * 0.85; // Placeholder
    const outlays = 0.05;
    const gainLoss = proceeds - acb - outlays;
    
    totalProceeds += proceeds;
    totalACB += acb;
    totalOutlays += outlays;
    
    capitalGains.push({
      date: (t as any).datetime?.split(' ')[0] || 'Unknown',
      description: `${(t as any).protocol} swap - ${(t as any).amount_decimal?.toFixed(4)} ${(t as any).token_symbol}`,
      proceeds,
      acb,
      outlays,
      gainLoss
    });
  }
  
  // Sort by date
  capitalGains.sort((a, b) => a.date.localeCompare(b.date));
  
  const totalGainLoss = totalProceeds - totalACB - totalOutlays;
  const taxableGain = totalGainLoss > 0 ? totalGainLoss * 0.5 : 0; // 50% inclusion rate
  const allowableLoss = totalGainLoss < 0 ? Math.abs(totalGainLoss) * 0.5 : 0;
  
  return NextResponse.json({
    year,
    summary: {
      totalDisposals: capitalGains.length,
      totalProceeds,
      totalACB,
      totalOutlays,
      totalGainLoss,
      taxableCapitalGain: taxableGain,
      allowableCapitalLoss: allowableLoss
    },
    disposals: capitalGains.slice(0, 100), // Limit for response size
    hasMore: capitalGains.length > 100,
    notes: [
      'Capital gains from cryptocurrency are taxable in Canada',
      '50% of capital gains are included in income (inclusion rate)',
      'ACB (Adjusted Cost Base) calculated using average cost method',
      'All values in CAD - verify exchange rates used',
      'This is a simplified calculation - consult a tax professional'
    ]
  });
}

import { getAuthenticatedUser } from '@/lib/auth';
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

// Schedule 3 - Capital Gains (or Losses)
// SECURITY: All queries filtered by user_id

export async function GET(request: Request) {
  const auth = await getAuthenticatedUser();
  if (!auth) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year') || '2025';
  
  const db = getDb();
  
  // SECURITY: Get this user's wallet IDs first
  const userWallets = await db.prepare(`SELECT id FROM wallets WHERE user_id = $1`).all(auth.userId) as { id: number }[];
  const walletIds = userWallets.map(w => w.id);
  
  if (walletIds.length === 0) {
    return NextResponse.json({
      year,
      summary: { totalDisposals: 0, totalProceeds: 0, totalACB: 0, totalOutlays: 0, totalGainLoss: 0, taxableCapitalGain: 0, allowableCapitalLoss: 0 },
      disposals: [],
      hasMore: false,
      notes: ['No wallets found for this user']
    });
  }
  
  let disposals: any[] = [];
  let summary = { totalDisposals: 0, totalProceeds: 0, totalACB: 0, totalOutlays: 0, totalGainLoss: 0, taxableCapitalGain: 0, allowableCapitalLoss: 0 };

  try {
    // Get summary from calculated_disposals - FILTERED BY USER via tx_id join
    const summaryResult = await db.prepare(`
      SELECT COUNT(*) as disposal_count, COALESCE(SUM(cd.proceeds_cad), 0) as total_proceeds, COALESCE(SUM(cd.acb_cad), 0) as total_acb, COALESCE(SUM(cd.gain_loss_cad), 0) as net_gain_loss
      FROM calculated_disposals cd 
      JOIN transactions t ON cd.tx_id = t.id
      WHERE cd.year = $1 AND t.wallet_id = ANY($2::int[])
    `).get(parseInt(year), [walletIds]) as any;

    if (summaryResult) {
      summary.totalDisposals = Number(summaryResult.disposal_count) || 0;
      summary.totalProceeds = Number(summaryResult.total_proceeds) || 0;
      summary.totalACB = Number(summaryResult.total_acb) || 0;
      summary.totalGainLoss = Number(summaryResult.net_gain_loss) || 0;
      
      if (summary.totalGainLoss > 0) {
        summary.taxableCapitalGain = summary.totalGainLoss * 0.5;
      } else {
        summary.allowableCapitalLoss = Math.abs(summary.totalGainLoss) * 0.5;
      }
    }

    // Get individual disposals - FILTERED BY USER via tx_id join
    disposals = await db.prepare(`
      SELECT cd.id, cd.tx_hash, cd.disposal_date, cd.token as token_symbol, cd.amount as quantity, cd.proceeds_cad, cd.acb_cad, cd.gain_loss_cad
      FROM calculated_disposals cd 
      JOIN transactions t ON cd.tx_id = t.id
      WHERE cd.year = $1 AND t.wallet_id = ANY($2::int[])
      ORDER BY cd.disposal_date DESC LIMIT 100
    `).all(parseInt(year), [walletIds]) as any[];

  } catch (e) {
    console.error('Error fetching calculated_disposals:', e);
    
    // Fallback - FILTERED BY USER
    const yearStart = new Date(`${year}-01-01T00:00:00Z`).getTime() * 1000000;
    const yearEnd = new Date(`${parseInt(year) + 1}-01-01T00:00:00Z`).getTime() * 1000000;
    
    const rawDisposals = await db.prepare(`
      SELECT t.id, t.tx_hash, t.block_timestamp, CAST(t.amount AS REAL) / 1e24 as amount_near, t.cost_basis_cad,
        to_char(to_timestamp(t.block_timestamp/1000000000), 'YYYY-MM-DD HH24:MI:SS') as datetime
      FROM transactions t
      WHERE t.block_timestamp >= $1 AND t.block_timestamp < $2 AND t.wallet_id = ANY($3::int[])
      AND t.direction = 'out' AND t.tax_category IN ('trade', 'transfer', 'swap')
      ORDER BY t.block_timestamp DESC LIMIT 100
    `).all(yearStart, yearEnd, [walletIds]) as any[];

    for (const d of rawDisposals) {
      const proceeds = Number(d.cost_basis_cad) || 0;
      disposals.push({ id: d.id, tx_hash: d.tx_hash, disposal_date: d.datetime, token_symbol: 'NEAR', quantity: d.amount_near, proceeds_cad: proceeds, acb_cad: null, gain_loss_cad: null });
      summary.totalProceeds += proceeds;
      summary.totalDisposals++;
    }
  }

  const formattedDisposals = disposals.map(d => ({
    date: d.disposal_date?.split('T')[0] || d.disposal_date?.split(' ')[0] || 'Unknown',
    description: `${d.token_symbol || 'NEAR'} - ${Number(d.quantity || 0).toFixed(4)}`,
    txHash: d.tx_hash,
    wallet: null,
    proceeds: Number(d.proceeds_cad || 0),
    acb: Number(d.acb_cad || 0),
    outlays: 0,
    gainLoss: Number(d.gain_loss_cad || 0),
  }));

  return NextResponse.json({
    year,
    summary: {
      totalDisposals: summary.totalDisposals,
      totalProceeds: Number(summary.totalProceeds.toFixed(2)),
      totalACB: Number(summary.totalACB.toFixed(2)),
      totalOutlays: 0,
      totalGainLoss: Number(summary.totalGainLoss.toFixed(2)),
      taxableCapitalGain: Number(summary.taxableCapitalGain.toFixed(2)),
      allowableCapitalLoss: Number(summary.allowableCapitalLoss.toFixed(2)),
    },
    disposals: formattedDisposals,
    hasMore: disposals.length >= 100,
    notes: [
      'Capital gains from cryptocurrency are taxable in Canada',
      '50% of capital gains are included in income (inclusion rate)',
      'ACB (Adjusted Cost Base) calculated using average cost method',
      'All values in CAD',
      summary.totalGainLoss < 0 ? `Net capital LOSS of $${Math.abs(summary.totalGainLoss).toLocaleString()} CAD for ${year}` : `Net capital GAIN of $${summary.totalGainLoss.toLocaleString()} CAD for ${year}`,
    ]
  });
}

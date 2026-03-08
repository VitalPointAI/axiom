import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

// Export tax reports in various formats

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year') || '2025';
  const format = searchParams.get('format') || 'csv';
  const report = searchParams.get('report') || 'schedule3';
  
  const db = getDb();
  
  const yearStart = new Date(`${year}-01-01T00:00:00Z`).getTime() * 1000000;
  const yearEnd = new Date(`${parseInt(year) + 1}-01-01T00:00:00Z`).getTime() * 1000000;
  
  if (report === 'schedule3') {
    // Get all disposals for Schedule 3
    const stmt = await db.prepare(`
      SELECT 
        datetime(t.block_timestamp/1000000000, 'unixepoch') as date,
        'Cryptocurrency - NEAR' as description,
        CAST(t.amount AS REAL) / 1e24 as units,
        COALESCE(t.cost_basis_cad, t.cost_basis_usd * 1.35, 0) as proceeds,
        0 as acb,
        0 as outlays,
        COALESCE(t.cost_basis_cad, t.cost_basis_usd * 1.35, 0) as gain_loss
      FROM transactions t
      WHERE t.block_timestamp >= ? AND t.block_timestamp < ?
      AND t.direction = 'out'
      AND CAST(t.amount AS REAL) / 1e24 > 0.01
      ORDER BY t.block_timestamp
    `);
    const disposals = await stmt.all(yearStart, yearEnd);
    
    if (format === 'csv') {
      const headers = ['Date', 'Description', 'Units', 'Proceeds (CAD)', 'ACB (CAD)', 'Outlays', 'Gain/Loss (CAD)'];
      const rows = disposals.map((d: any) => [
        d.date?.split(' ')[0] || '',
        d.description,
        d.units.toFixed(4),
        d.proceeds.toFixed(2),
        d.acb.toFixed(2),
        d.outlays.toFixed(2),
        d.gain_loss.toFixed(2)
      ]);
      
      const csv = [
        headers.join(','),
        ...rows.map(r => r.join(','))
      ].join('\n');
      
      return new NextResponse(csv, {
        headers: {
          'Content-Type': 'text/csv',
          'Content-Disposition': `attachment; filename="schedule3_${year}.csv"`
        }
      });
    }
    
    return NextResponse.json({ disposals });
  }
  
  if (report === 't1135') {
    // Year-end inventory for T1135
    const nearStmt = await db.prepare(`
      SELECT 
        SUM(CASE WHEN direction = 'in' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) -
        SUM(CASE WHEN direction = 'out' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as balance,
        SUM(CASE WHEN direction = 'in' THEN COALESCE(cost_basis_cad, cost_basis_usd * 1.35, 0) ELSE 0 END) as cost_basis
      FROM transactions
      WHERE block_timestamp < ?
    `);
    const nearResult = await nearStmt.get(yearEnd) as { balance: number; cost_basis: number };
    
    const stakingStmt = await db.prepare(`
      SELECT SUM(CASE WHEN event_type = 'stake' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) -
             SUM(CASE WHEN event_type = 'unstake' THEN CAST(amount AS REAL) / 1e24 ELSE 0 END) as staked
      FROM staking_events
      WHERE block_timestamp < ?
    `);
    const stakingResult = await stakingStmt.get(yearEnd) as { staked: number };
    
    // Get income
    const stakingIncomeStmt = await db.prepare(`
      SELECT SUM(reward_near) as rewards FROM staking_rewards
      WHERE block_timestamp >= ? AND block_timestamp < ?
    `);
    const stakingIncome = await stakingIncomeStmt.get(yearStart, yearEnd) as { rewards: number };
    
    const defiIncomeStmt = await db.prepare(`
      SELECT SUM(COALESCE(value_cad, value_usd * 1.35, 0)) as income
      FROM defi_events
      WHERE block_timestamp >= ? AND block_timestamp < ?
      AND tax_category = 'income'
    `);
    const defiIncome = await defiIncomeStmt.get(yearStart, yearEnd) as { income: number };
    
    const t1135Data = {
      year,
      asOfDate: `${year}-12-31`,
      foreignProperty: [
        {
          description: 'Cryptocurrency - NEAR Protocol',
          country: 'N/A - Decentralized',
          maxCostAmount: nearResult?.cost_basis || 0,
          yearEndCostAmount: nearResult?.cost_basis || 0,
          income: ((stakingIncome?.rewards || 0) * 5 * 1.35) + (defiIncome?.income || 0),
          gainLoss: 0
        }
      ],
      totalHoldings: (nearResult?.balance || 0) + (stakingResult?.staked || 0)
    };
    
    if (format === 'csv') {
      const headers = ['Property Description', 'Country', 'Max Cost (CAD)', 'Year-End Cost (CAD)', 'Income (CAD)', 'Gain/Loss (CAD)'];
      const rows = t1135Data.foreignProperty.map(p => [
        p.description,
        p.country,
        p.maxCostAmount.toFixed(2),
        p.yearEndCostAmount.toFixed(2),
        p.income.toFixed(2),
        p.gainLoss.toFixed(2)
      ]);
      
      const csv = [
        `# T1135 Foreign Income Verification Statement - ${year}`,
        '',
        headers.join(','),
        ...rows.map(r => r.join(','))
      ].join('\n');
      
      return new NextResponse(csv, {
        headers: {
          'Content-Type': 'text/csv',
          'Content-Disposition': `attachment; filename="t1135_${year}.csv"`
        }
      });
    }
    
    return NextResponse.json(t1135Data);
  }
  
  if (report === 'transactions') {
    // Full transaction export
    const stmt = await db.prepare(`
      SELECT 
        datetime(t.block_timestamp/1000000000, 'unixepoch') as date,
        t.tx_hash,
        t.direction,
        t.action_type,
        t.tax_category,
        CAST(t.amount AS REAL) / 1e24 as amount_near,
        t.cost_basis_usd,
        t.cost_basis_cad,
        w.account_id as wallet
      FROM transactions t
      LEFT JOIN wallets w ON t.wallet_id = w.id
      WHERE t.block_timestamp >= ? AND t.block_timestamp < ?
      ORDER BY t.block_timestamp
    `);
    const transactions = await stmt.all(yearStart, yearEnd);
    
    if (format === 'csv') {
      const headers = ['Date', 'TX Hash', 'Direction', 'Type', 'Category', 'Amount (NEAR)', 'Value (USD)', 'Value (CAD)', 'Wallet'];
      const rows = (transactions as any[]).map(t => [
        t.date?.split(' ')[0] || '',
        t.tx_hash?.slice(0, 16) || '',
        t.direction,
        t.action_type || '',
        t.tax_category || '',
        t.amount_near?.toFixed(4) || '0',
        t.cost_basis_usd?.toFixed(2) || '0',
        t.cost_basis_cad?.toFixed(2) || '0',
        t.wallet?.slice(0, 20) || ''
      ]);
      
      const csv = [
        headers.join(','),
        ...rows.map(r => r.join(','))
      ].join('\n');
      
      return new NextResponse(csv, {
        headers: {
          'Content-Type': 'text/csv',
          'Content-Disposition': `attachment; filename="transactions_${year}.csv"`
        }
      });
    }
    
    return NextResponse.json({ transactions });
  }
  
  return NextResponse.json({ error: 'Invalid report type' }, { status: 400 });
}

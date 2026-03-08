import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const year = searchParams.get('year');
  
  const db = getDb();
  
  // Summary by year
  let summary;
  if (year) {
    summary = await db.prepare(`
      SELECT tax_year, 
             SUM(reward_near) as total_near,
             SUM(income_usd) as total_usd,
             SUM(income_cad) as total_cad,
             COUNT(*) as days
      FROM staking_income 
      WHERE tax_year = ?
      GROUP BY tax_year
    `).all(year);
  } else {
    summary = await db.prepare(`
      SELECT tax_year, 
             SUM(reward_near) as total_near,
             SUM(income_usd) as total_usd,
             SUM(income_cad) as total_cad,
             COUNT(*) as days
      FROM staking_income 
      GROUP BY tax_year
      ORDER BY tax_year
    `).all();
  }
  
  // By validator
  let byValidator;
  if (year) {
    byValidator = await db.prepare(`
      SELECT validator,
             SUM(reward_near) as total_near,
             SUM(income_usd) as total_usd,
             SUM(income_cad) as total_cad,
             MIN(date) as start_date,
             MAX(date) as end_date
      FROM staking_income
      WHERE tax_year = ?
      GROUP BY validator
      ORDER BY total_near DESC
    `).all(year);
  } else {
    byValidator = await db.prepare(`
      SELECT validator,
             SUM(reward_near) as total_near,
             SUM(income_usd) as total_usd,
             SUM(income_cad) as total_cad,
             MIN(date) as start_date,
             MAX(date) as end_date
      FROM staking_income
      GROUP BY validator
      ORDER BY total_near DESC
    `).all();
  }
  
  // Monthly breakdown for selected year
  let monthly: any[] = [];
  if (year) {
    monthly = await db.prepare(`
      SELECT 
        substr(date, 1, 7) as month,
        SUM(reward_near) as total_near,
        SUM(income_usd) as total_usd,
        SUM(income_cad) as total_cad
      FROM staking_income
      WHERE tax_year = ?
      GROUP BY substr(date, 1, 7)
      ORDER BY month
    `).all(year);
  }
  
  // Grand totals
  const totals = await db.prepare(`
    SELECT 
      SUM(reward_near) as total_near,
      SUM(income_usd) as total_usd,
      SUM(income_cad) as total_cad,
      COUNT(*) as total_days
    FROM staking_income
  `).get();
  
  return NextResponse.json({
    summary,
    byValidator,
    monthly,
    totals,
  });
}

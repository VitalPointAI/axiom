const Database = require('better-sqlite3');
const db = new Database('/home/deploy/neartax/neartax.db');

console.log('=== ALL UNIQUE TRANSACTION PATTERNS ===\n');

// Get all unique patterns
const patterns = db.prepare(`
  SELECT 
    action_type,
    method_name,
    direction,
    COUNT(*) as cnt,
    SUM(CAST(amount AS REAL)/1e24) as total_near
  FROM transactions
  GROUP BY action_type, method_name, direction
  ORDER BY cnt DESC
`).all();

console.log('action_type | method_name | direction | count | total_near');
console.log('-'.repeat(80));
patterns.forEach(p => {
  const action = (p.action_type || 'NULL').padEnd(20);
  const method = (p.method_name || '-').padEnd(25);
  const dir = p.direction.padEnd(5);
  const cnt = String(p.cnt).padStart(8);
  const near = (p.total_near?.toFixed(2) || '0').padStart(15);
  console.log(`${action} ${method} ${dir} ${cnt} ${near}`);
});

console.log('\n\n=== UNIQUE COUNTERPARTY PATTERNS ===\n');

// Get counterparty patterns
const counterparties = db.prepare(`
  SELECT 
    CASE 
      WHEN counterparty LIKE '%.poolv1.near' THEN '*.poolv1.near'
      WHEN counterparty LIKE '%.pool.near' THEN '*.pool.near'
      WHEN counterparty LIKE '%.cdao.near' THEN '*.cdao.near'
      WHEN counterparty LIKE '%.sputnikdao.near' THEN '*.sputnikdao.near'
      WHEN LENGTH(counterparty) = 64 AND counterparty GLOB '[0-9a-f]*' THEN '[implicit_account]'
      WHEN counterparty LIKE '%.near' THEN counterparty
      ELSE counterparty
    END as pattern,
    direction,
    COUNT(*) as cnt,
    SUM(CAST(amount AS REAL)/1e24) as total_near
  FROM transactions
  GROUP BY pattern, direction
  HAVING cnt >= 5
  ORDER BY cnt DESC
  LIMIT 50
`).all();

console.log('counterparty_pattern | direction | count | total_near');
console.log('-'.repeat(80));
counterparties.forEach(p => {
  const pattern = p.pattern.padEnd(40);
  const dir = p.direction.padEnd(5);
  const cnt = String(p.cnt).padStart(8);
  const near = (p.total_near?.toFixed(2) || '0').padStart(15);
  console.log(`${pattern} ${dir} ${cnt} ${near}`);
});

console.log('\n\n=== UNIQUE METHOD NAMES ===\n');

const methods = db.prepare(`
  SELECT 
    method_name,
    COUNT(*) as cnt
  FROM transactions
  WHERE method_name IS NOT NULL
  GROUP BY method_name
  ORDER BY cnt DESC
`).all();

methods.forEach(m => {
  console.log(`${m.method_name}: ${m.cnt}`);
});

db.close();

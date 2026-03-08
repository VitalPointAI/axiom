import { Pool } from 'pg';

let pool: Pool | null = null;

export function getPool(): Pool {
  if (!pool) {
    pool = new Pool({
      connectionString: process.env.DATABASE_URL || 'postgres://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax',
    });
  }
  return pool;
}

function convertSql(sql: string): string {
  let i = 0;
  return sql
    // Convert ? placeholders to $1, $2, etc
    .replace(/\?/g, () => '$' + (++i))
    // SQLite datetime('now') -> PostgreSQL NOW()
    .replace(/datetime\(['"]now['"]\)/gi, 'NOW()')
    // SQLite datetime(column, modifier) -> PostgreSQL equivalent
    .replace(/datetime\(([^,]+),\s*['"]([^'"]+)['"]\)/gi, "($1 + INTERVAL '$2')")
    // SQLite CAST AS REAL -> PostgreSQL CAST AS DOUBLE PRECISION
    .replace(/CAST\(([^)]+)\s+AS\s+REAL\)/gi, 'CAST($1 AS DOUBLE PRECISION)')
    // SQLite strftime -> PostgreSQL to_char (basic)
    .replace(/strftime\(['"]%Y['"],\s*([^)]+)\)/gi, "EXTRACT(YEAR FROM $1)::TEXT");
}

export function getDb() {
  const p = getPool();
  
  return {
    prepare: (sql: string) => {
      const pgSql = convertSql(sql);
      return {
        get: async (...params: any[]) => {
          const result = await p.query(pgSql, params);
          return result.rows[0];
        },
        all: async (...params: any[]) => {
          const result = await p.query(pgSql, params);
          return result.rows;
        },
        run: async (...params: any[]) => {
          const result = await p.query(pgSql, params);
          return { rowCount: result.rowCount, lastInsertRowid: result.rows[0]?.id };
        },
      };
    },
    exec: async (sql: string) => {
      await p.query(sql);
    },
    pragma: () => {},
    query: (sql: string, params?: any[]) => p.query(convertSql(sql), params),
  };
}

export async function closeDb() {
  if (pool) {
    await pool.end();
    pool = null;
  }
}

export const db = {
  query: async (sql: string) => {
    const p = getPool();
    return await p.query(sql);
  }
};

export { Pool };

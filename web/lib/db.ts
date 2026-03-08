import { Pool, QueryResult, PoolClient } from 'pg';

// Create a connection pool
const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 
    `postgres://${process.env.PGUSER}:${process.env.PGPASSWORD}@${process.env.PGHOST}:${process.env.PGPORT}/${process.env.PGDATABASE}`,
  max: 20,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 2000,
});

// Log connection errors
pool.on('error', (err) => {
  console.error('Unexpected PostgreSQL pool error:', err);
});

// Convert ? placeholders to $1, $2, etc for PostgreSQL
function convertPlaceholders(sql: string): string {
  let idx = 0;
  return sql.replace(/\?/g, () => `$${++idx}`);
}

// Main async database interface
export const db = {
  /**
   * Execute a query and return all rows
   */
  async all<T = Record<string, any>>(sql: string, params: any[] = []): Promise<T[]> {
    const pgSql = convertPlaceholders(sql);
    const result = await pool.query(pgSql, params);
    return result.rows as T[];
  },

  /**
   * Execute a query and return the first row
   */
  async get<T = Record<string, any>>(sql: string, params: any[] = []): Promise<T | undefined> {
    const rows = await this.all<T>(sql, params);
    return rows[0];
  },

  /**
   * Execute a write query (INSERT, UPDATE, DELETE)
   */
  async run(sql: string, params: any[] = []): Promise<{ changes: number; lastInsertRowid?: number }> {
    const pgSql = convertPlaceholders(sql);
    
    // For INSERTs, try to get the inserted ID
    if (sql.trim().toUpperCase().startsWith('INSERT')) {
      try {
        const result = await pool.query(pgSql + ' RETURNING id', params);
        return {
          changes: result.rowCount || 0,
          lastInsertRowid: result.rows[0]?.id
        };
      } catch (e) {
        // If RETURNING fails (e.g., table has no id column), fall back
        const result = await pool.query(pgSql, params);
        return { changes: result.rowCount || 0 };
      }
    }
    
    const result = await pool.query(pgSql, params);
    return { changes: result.rowCount || 0 };
  },

  /**
   * Execute raw SQL (for DDL, etc.)
   */
  async exec(sql: string): Promise<void> {
    await pool.query(sql);
  },

  /**
   * Run a transaction
   */
  async transaction<T>(fn: (client: PoolClient) => Promise<T>): Promise<T> {
    const client = await pool.connect();
    try {
      await client.query('BEGIN');
      const result = await fn(client);
      await client.query('COMMIT');
      return result;
    } catch (e) {
      await client.query('ROLLBACK');
      throw e;
    } finally {
      client.release();
    }
  },

  /**
   * Get a raw pool client for complex operations
   */
  async getClient(): Promise<PoolClient> {
    return pool.connect();
  },

  /**
   * Raw query access
   */
  async query(sql: string, params?: any[]): Promise<QueryResult> {
    const pgSql = convertPlaceholders(sql);
    return pool.query(pgSql, params);
  },

  /**
   * Close the pool (for cleanup)
   */
  async close(): Promise<void> {
    await pool.end();
  }
};

// Legacy compatibility - getDb() returns a sync-looking interface
// NOTE: This is a compatibility shim. All new code should use the async `db` object
interface PreparedStatement {
  run: (...params: any[]) => { lastInsertRowid: number; changes: number };
  get: (...params: any[]) => any;
  all: (...params: any[]) => any[];
}

interface SyncDb {
  prepare: (sql: string) => PreparedStatement;
  exec: (sql: string) => void;
}

// Helper to flatten params - handles both .all(a, b, c) and .all([a, b, c]) patterns
function flattenParams(params: any[]): any[] {
  // If called with a single array argument, use that array directly
  if (params.length === 1 && Array.isArray(params[0])) {
    return params[0];
  }
  // Otherwise return params as-is (handles .all(a, b, c) pattern)
  return params;
}

// This creates a "sync" wrapper that actually returns promises
// For true sync behavior, would need a different approach
// Most Next.js API routes can handle async anyway
export function getDb(): { 
  exec: (sql: string) => Promise<void>;
  prepare: (sql: string) => { 
    all: (...params: any[]) => Promise<any[]>; 
    get: (...params: any[]) => Promise<any>; 
    run: (...params: any[]) => Promise<any> 
  } 
} {
  return {
    async exec(sql: string) {
      await db.exec(sql);
    },
    prepare(sql: string) {
      return {
        async all(...params: any[]) {
          return db.all(sql, flattenParams(params));
        },
        async get(...params: any[]) {
          return db.get(sql, flattenParams(params));
        },
        async run(...params: any[]) {
          return db.run(sql, flattenParams(params));
        }
      };
    }
  };
}

export default db;

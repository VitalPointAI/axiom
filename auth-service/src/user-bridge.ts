/**
 * User Bridge — maps near-phantom-auth users to Axiom's `users` table.
 *
 * near-phantom-auth creates UUID-based user records in anon_users/oauth_users.
 * Axiom's existing data model uses integer serial IDs in the `users` table.
 * This bridge ensures every auth user has a corresponding Axiom user row.
 */

import pg from 'pg';

const { Pool } = pg;

export interface AxiomUserBridge {
  initialize(): Promise<void>;
  syncUser(authData: Record<string, unknown>): Promise<number>;
  getAxiomUserId(authUserId: string): Promise<number | null>;
}

export function createAxiomUserBridge(connectionString: string): AxiomUserBridge {
  const pool = new Pool({ connectionString });

  return {
    async initialize() {
      // Create mapping table if it doesn't exist
      await pool.query(`
        CREATE TABLE IF NOT EXISTS auth_user_mapping (
          auth_user_id TEXT PRIMARY KEY,
          axiom_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          user_type TEXT NOT NULL DEFAULT 'anonymous',
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_auth_user_mapping_axiom
          ON auth_user_mapping(axiom_user_id);
      `);
    },

    async syncUser(authData: Record<string, unknown>): Promise<number> {
      const authUserId = authData.userId as string || authData.id as string;
      const codename = authData.codename as string | undefined;
      const email = authData.email as string | undefined;
      const nearAccountId = authData.nearAccountId as string | undefined;
      const username = authData.username as string | undefined;
      const userType = authData.type as string || 'anonymous';

      if (!authUserId) return -1;

      const client = await pool.connect();
      try {
        await client.query('BEGIN');

        // Check if mapping already exists
        const existing = await client.query(
          'SELECT axiom_user_id FROM auth_user_mapping WHERE auth_user_id = $1',
          [authUserId]
        );

        if (existing.rows.length > 0) {
          // Update Axiom user with latest info
          const axiomUserId = existing.rows[0].axiom_user_id;
          await client.query(`
            UPDATE users SET
              near_account_id = COALESCE($1, near_account_id),
              email = COALESCE($2, email),
              codename = COALESCE($3, codename),
              username = COALESCE($4, username)
            WHERE id = $5
          `, [nearAccountId, email, codename, username, axiomUserId]);

          await client.query('COMMIT');
          return axiomUserId;
        }

        // Try to find existing Axiom user by email or near_account_id
        let axiomUserId: number | null = null;

        if (email) {
          const byEmail = await client.query(
            'SELECT id FROM users WHERE email = $1',
            [email]
          );
          if (byEmail.rows.length > 0) axiomUserId = byEmail.rows[0].id;
        }

        if (!axiomUserId && nearAccountId) {
          const byNear = await client.query(
            'SELECT id FROM users WHERE near_account_id = $1',
            [nearAccountId]
          );
          if (byNear.rows.length > 0) axiomUserId = byNear.rows[0].id;
        }

        if (!axiomUserId && codename) {
          const byCodename = await client.query(
            'SELECT id FROM users WHERE codename = $1',
            [codename]
          );
          if (byCodename.rows.length > 0) axiomUserId = byCodename.rows[0].id;
        }

        // Create new Axiom user if not found
        if (!axiomUserId) {
          const insert = await client.query(`
            INSERT INTO users (near_account_id, email, codename, username)
            VALUES ($1, $2, $3, $4)
            RETURNING id
          `, [nearAccountId, email, codename, username]);
          axiomUserId = insert.rows[0].id;
        } else {
          // Update existing user with any new info
          await client.query(`
            UPDATE users SET
              near_account_id = COALESCE($1, near_account_id),
              email = COALESCE($2, email),
              codename = COALESCE($3, codename),
              username = COALESCE($4, username)
            WHERE id = $5
          `, [nearAccountId, email, codename, username, axiomUserId]);
        }

        // Create mapping
        await client.query(`
          INSERT INTO auth_user_mapping (auth_user_id, axiom_user_id, user_type)
          VALUES ($1, $2, $3)
          ON CONFLICT (auth_user_id) DO NOTHING
        `, [authUserId, axiomUserId, userType]);

        await client.query('COMMIT');
        return axiomUserId!;
      } catch (err) {
        await client.query('ROLLBACK');
        throw err;
      } finally {
        client.release();
      }
    },

    async getAxiomUserId(authUserId: string): Promise<number | null> {
      const result = await pool.query(
        'SELECT axiom_user_id FROM auth_user_mapping WHERE auth_user_id = $1',
        [authUserId]
      );
      return result.rows.length > 0 ? result.rows[0].axiom_user_id : null;
    },
  };
}

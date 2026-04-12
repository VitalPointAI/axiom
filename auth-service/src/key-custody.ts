/**
 * key-custody.ts
 *
 * Key custody operations for the post-quantum encryption at rest feature (D-26, D-27).
 *
 * Responsibilities:
 *   - provisionUserKeys: call FastAPI keygen + write ML-KEM blobs to users row
 *   - getUserKeyBundle: SELECT the three ML-KEM blobs from users row
 *   - resolveSessionDek: call FastAPI unwrap-session-dek + upsert session_dek_cache row
 *   - deleteSessionDekCache: DELETE session_dek_cache row on logout
 *
 * Design note: core functions are implemented in a DI factory (_createKeyCustody)
 * so tests can pass mock pool + client dependencies without ESM module mocking.
 * The module-level exports wrap the factory with real production dependencies.
 *
 * Environment variables:
 *   SESSION_LIFETIME_SECONDS  — default 86400 (24h); controls expires_at in session_dek_cache
 *   AXIOM_DB_URL / DATABASE_URL — used to create the production pool (read by getPool)
 */

import pg from 'pg';
import {
  internalKeygen,
  internalUnwrapSessionDek,
  internalRewrapDek,
  type KeygenResult,
} from './internal-crypto-client.js';

const { Pool } = pg;

// ---------------------------------------------------------------------------
// Pool singleton for key-custody operations
// ---------------------------------------------------------------------------
// key-custody.ts does NOT import from user-bridge.ts to avoid circular deps.
// It maintains its own Pool created from AXIOM_DB_URL / DATABASE_URL.
// user-bridge.ts calls provisionUserKeys() after importing from key-custody.ts.

let _kcPool: InstanceType<typeof Pool> | null = null;

function getPool(): InstanceType<typeof Pool> {
  if (!_kcPool) {
    const connStr = process.env.AXIOM_DB_URL ?? process.env.DATABASE_URL;
    if (!connStr) {
      throw new Error(
        'AXIOM_DB_URL or DATABASE_URL must be set for key-custody operations',
      );
    }
    _kcPool = new Pool({ connectionString: connStr });
  }
  return _kcPool;
}

const SESSION_LIFETIME_SECONDS = Number(
  process.env.SESSION_LIFETIME_SECONDS ?? 60 * 60 * 24,
); // 24h default

// ---------------------------------------------------------------------------
// DI factory — used by tests; production exports wrap this with real deps
// ---------------------------------------------------------------------------

/**
 * Create a key-custody object bound to specific pool + crypto client dependencies.
 * Used by unit tests to inject mock dependencies.
 */
export function _createKeyCustody(
  pool: pg.Pool,
  keygenFn: (sealingKey: Buffer) => Promise<KeygenResult>,
  unwrapFn: (
    sealingKey: Buffer,
    mlkemSealedDk: Buffer,
    wrappedDek: Buffer,
  ) => Promise<Buffer>,
) {
  return {
    /**
     * Call FastAPI keygen and store the three blobs on the users row.
     * Called by syncUser on first user creation (D-11).
     */
    async provisionUserKeys(userId: number, sealingKey: Buffer): Promise<KeygenResult> {
      const result = await keygenFn(sealingKey);
      await pool.query(
        `UPDATE users SET mlkem_ek = $1, mlkem_sealed_dk = $2, wrapped_dek = $3 WHERE id = $4`,
        [result.mlkemEk, result.mlkemSealedDk, result.wrappedDek, userId],
      );
      return result;
    },

    /**
     * SELECT the three ML-KEM blobs from the users row.
     * Returns null if the row doesn't exist or any blob is null (pre-migration users).
     */
    async getUserKeyBundle(userId: number): Promise<KeygenResult | null> {
      const { rows } = await pool.query(
        `SELECT mlkem_ek, mlkem_sealed_dk, wrapped_dek FROM users WHERE id = $1`,
        [userId],
      );
      if (rows.length === 0) return null;
      const r = rows[0];
      if (!r['mlkem_ek'] || !r['mlkem_sealed_dk'] || !r['wrapped_dek']) return null;
      return {
        mlkemEk: Buffer.from(r['mlkem_ek'] as Buffer),
        mlkemSealedDk: Buffer.from(r['mlkem_sealed_dk'] as Buffer),
        wrappedDek: Buffer.from(r['wrapped_dek'] as Buffer),
      };
    },

    /**
     * Unwrap the user's session DEK and upsert a session_dek_cache row (D-26).
     * Called by server.ts login handler after session creation.
     *
     * The sealing_key Buffer should be .fill(0)'d by the caller after this returns.
     */
    async resolveSessionDek(
      userId: number,
      sessionId: string,
      sealingKey: Buffer,
    ): Promise<void> {
      // Reuse getUserKeyBundle through pool
      const { rows } = await pool.query(
        `SELECT mlkem_ek, mlkem_sealed_dk, wrapped_dek FROM users WHERE id = $1`,
        [userId],
      );
      if (rows.length === 0 || !rows[0]['mlkem_ek']) {
        throw new Error(
          `User ${userId} has no key bundle — cannot resolve session DEK`,
        );
      }
      const r = rows[0];
      const mlkemSealedDk = Buffer.from(r['mlkem_sealed_dk'] as Buffer);
      const wrappedDek = Buffer.from(r['wrapped_dek'] as Buffer);

      const sessionWrapped = await unwrapFn(sealingKey, mlkemSealedDk, wrappedDek);
      const expiresAt = new Date(Date.now() + SESSION_LIFETIME_SECONDS * 1000);

      try {
        await pool.query(
          `INSERT INTO session_dek_cache (session_id, encrypted_dek, expires_at)
           VALUES ($1, $2, $3)
           ON CONFLICT (session_id) DO UPDATE
             SET encrypted_dek = EXCLUDED.encrypted_dek,
                 expires_at    = EXCLUDED.expires_at`,
          [sessionId, sessionWrapped, expiresAt],
        );
      } finally {
        // Zero the session-wrapped blob — disciplined cleanup (T-16-16)
        sessionWrapped.fill(0);
      }
    },

    /**
     * DELETE the session_dek_cache row for the given session.
     * Called by server.ts logout handler (D-26).
     */
    async deleteSessionDekCache(sessionId: string): Promise<void> {
      await pool.query(
        `DELETE FROM session_dek_cache WHERE session_id = $1`,
        [sessionId],
      );
    },
  };
}

// ---------------------------------------------------------------------------
// Production singleton (uses real pool from user-bridge + real IPC client)
// ---------------------------------------------------------------------------

let _custody: ReturnType<typeof _createKeyCustody> | null = null;

function getCustody() {
  if (!_custody) {
    _custody = _createKeyCustody(getPool(), internalKeygen, internalUnwrapSessionDek);
  }
  return _custody;
}

// ---------------------------------------------------------------------------
// Module-level convenience exports (production use)
// ---------------------------------------------------------------------------

export async function provisionUserKeys(
  userId: number,
  sealingKey: Buffer,
): Promise<KeygenResult> {
  return getCustody().provisionUserKeys(userId, sealingKey);
}

export async function getUserKeyBundle(
  userId: number,
): Promise<KeygenResult | null> {
  return getCustody().getUserKeyBundle(userId);
}

export async function resolveSessionDek(
  userId: number,
  sessionId: string,
  sealingKey: Buffer,
): Promise<void> {
  return getCustody().resolveSessionDek(userId, sessionId, sealingKey);
}

export async function deleteSessionDekCache(sessionId: string): Promise<void> {
  return getCustody().deleteSessionDekCache(sessionId);
}

// Re-export rewrapDek for accountant access (D-25)
export { internalRewrapDek };

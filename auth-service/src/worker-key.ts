/**
 * worker-key.ts
 *
 * Opt-in background worker key operations (D-17, D-19).
 *
 * Architecture correction (plan 16-07): worker_sealed_dek is now AES-256-GCM
 * sealed with WORKER_KEY_WRAP_KEY (a server-held 32-byte env var), NOT with
 * the user's ML-KEM public key. This allows the worker process to unseal the
 * DEK without any active user session — which is the whole point of the opt-in
 * mode.
 *
 * The privacy trade-off is explicit: users who enable background processing are
 * trusting the server to hold a decryption key sealed with WORKER_KEY_WRAP_KEY.
 * Users who keep the default (off) have no server-side decryption capability.
 * See D-17, D-19, T-16-39.
 *
 * createWorkerKey: reads session_dek_cache → calls internalSealWorkerDek → store in users.worker_sealed_dek
 * revokeWorkerKey: clear worker_sealed_dek and worker_key_enabled = false
 *
 * Both operations write an audit_log row (T-16-41: repudiation mitigation).
 *
 * Design: _createWorkerKeyOps DI factory for unit-testable injection.
 * Production exports wrap the factory with real pool + client deps.
 */

import pg from 'pg';
import { internalSealWorkerDek } from './internal-crypto-client.js';

const { Pool } = pg;

// ---------------------------------------------------------------------------
// Pool singleton for worker-key operations
// ---------------------------------------------------------------------------

let _wkPool: InstanceType<typeof Pool> | null = null;

function getPool(): InstanceType<typeof Pool> {
  if (!_wkPool) {
    const connStr = process.env.AXIOM_DB_URL ?? process.env.DATABASE_URL;
    if (!connStr) {
      throw new Error(
        'AXIOM_DB_URL or DATABASE_URL must be set for worker-key operations',
      );
    }
    _wkPool = new Pool({ connectionString: connStr });
  }
  return _wkPool;
}

// ---------------------------------------------------------------------------
// DI factory — used by tests
// ---------------------------------------------------------------------------

/**
 * Create worker-key operations bound to injected dependencies.
 * Used by unit tests; production exports use real deps.
 */
export function _createWorkerKeyOps(
  pool: pg.Pool,
  sealFn: (sessionDekWrapped: Buffer) => Promise<Buffer>,
) {
  return {
    /**
     * Create an opt-in background worker DEK for the user (D-17).
     *
     * Workflow:
     *   1. Read the session-wrapped DEK from session_dek_cache for this session
     *   2. Call /internal/crypto/seal-worker-dek to convert to worker-sealed form
     *   3. UPDATE users SET worker_sealed_dek = $1, worker_key_enabled = TRUE
     *   4. INSERT audit_log row (T-16-41)
     *
     * @param userId       Axiom users.id
     * @param sessionId    The current session ID (used to look up session_dek_cache row)
     */
    async createWorkerKey(userId: number, sessionId: string): Promise<void> {
      // Step 1: load session-wrapped DEK from session_dek_cache
      const { rows } = await pool.query(
        `SELECT encrypted_dek FROM session_dek_cache WHERE session_id = $1`,
        [sessionId],
      );
      if (rows.length === 0 || !rows[0]['encrypted_dek']) {
        throw new Error(`No session DEK found for session ${sessionId} — cannot create worker key`);
      }
      const sessionDekWrapped = Buffer.from(rows[0]['encrypted_dek'] as Buffer);

      // Step 2: re-wrap with WORKER_KEY_WRAP_KEY (server-held; no ML-KEM)
      const workerSealed = await sealFn(sessionDekWrapped);

      // Zero the intermediate form immediately after the IPC call
      sessionDekWrapped.fill(0);

      try {
        // Step 3: persist worker blob
        await pool.query(
          `UPDATE users
           SET worker_sealed_dek = $1, worker_key_enabled = TRUE
           WHERE id = $2`,
          [workerSealed, userId],
        );

        // Step 4: audit (T-16-41)
        await pool.query(
          `INSERT INTO audit_log
             (user_id, entity_type, entity_id, action, actor_type, created_at)
           VALUES ($1, 'user', $1, 'worker_key_enabled', 'user', NOW())`,
          [userId],
        );
      } finally {
        // Zero the worker sealed blob after DB write (T-16-16)
        workerSealed.fill(0);
      }
    },

    /**
     * Revoke the opt-in background worker key (D-17).
     *
     * Sets worker_sealed_dek = NULL and worker_key_enabled = FALSE.
     * Writes an audit_log row (T-16-41).
     *
     * @param userId  Axiom users.id
     */
    async revokeWorkerKey(userId: number): Promise<void> {
      await pool.query(
        `UPDATE users
         SET worker_sealed_dek = NULL, worker_key_enabled = FALSE
         WHERE id = $1`,
        [userId],
      );

      await pool.query(
        `INSERT INTO audit_log
           (user_id, entity_type, entity_id, action, actor_type, created_at)
         VALUES ($1, 'user', $1, 'worker_key_revoked', 'user', NOW())`,
        [userId],
      );
    },
  };
}

// ---------------------------------------------------------------------------
// Production exports (use real pool + real IPC client)
// ---------------------------------------------------------------------------

let _workerKeyOps: ReturnType<typeof _createWorkerKeyOps> | null = null;

function getWorkerKeyOps() {
  if (!_workerKeyOps) {
    _workerKeyOps = _createWorkerKeyOps(
      getPool(),
      internalSealWorkerDek,
    );
  }
  return _workerKeyOps;
}

/**
 * Create an opt-in background worker DEK.
 *
 * @param userId    Axiom users.id
 * @param sessionId Current session ID (to look up session_dek_cache)
 */
export async function createWorkerKey(userId: number, sessionId: string): Promise<void> {
  return getWorkerKeyOps().createWorkerKey(userId, sessionId);
}

export async function revokeWorkerKey(userId: number): Promise<void> {
  return getWorkerKeyOps().revokeWorkerKey(userId);
}

/**
 * worker-key.ts
 *
 * Opt-in background worker key operations (D-17, D-19).
 *
 * createWorkerKey: unwrap user's DEK → re-wrap with own ek → store as worker_sealed_dek
 * revokeWorkerKey: clear worker_sealed_dek and worker_key_enabled = false
 *
 * Both operations write an audit_log row (T-16-19: repudiation mitigation).
 *
 * NOTE: worker_sealed_dek and worker_key_enabled columns do not exist until
 * migration 022 (plan 16-04). These operations will fail at the DB level until
 * then — that is expected and acceptable (fail-closed).
 *
 * Design: _createWorkerKeyOps DI factory for unit-testable injection.
 * Production exports wrap the factory with real pool + client deps.
 */

import pg from 'pg';
import {
  internalUnwrapSessionDek,
  internalRewrapDek,
  type KeygenResult,
} from './internal-crypto-client.js';
import { getUserKeyBundle } from './key-custody.js';

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
  getBundleFn: (userId: number) => Promise<KeygenResult | null>,
  unwrapFn: (
    sealingKey: Buffer,
    mlkemSealedDk: Buffer,
    wrappedDek: Buffer,
  ) => Promise<Buffer>,
  rewrapFn: (
    sessionDekWrapped: Buffer,
    granteeMlkemEk: Buffer,
  ) => Promise<Buffer>,
) {
  return {
    /**
     * Create an opt-in background worker DEK for the user (D-17).
     *
     * Workflow:
     *   1. Load the user's key bundle (mlkemSealedDk, wrappedDek, mlkemEk)
     *   2. Call /internal/crypto/unwrap-session-dek to get a session-wrapped DEK
     *   3. Call /internal/crypto/rewrap-dek with the user's OWN mlkemEk
     *      → produces a worker-bound ML-KEM blob independent of any session
     *   4. UPDATE users SET worker_sealed_dek = $1, worker_key_enabled = TRUE
     *   5. INSERT audit_log row (T-16-19)
     *
     * @param userId     Axiom users.id
     * @param sealingKey 32-byte key from near-phantom-auth passkey material
     */
    async createWorkerKey(userId: number, sealingKey: Buffer): Promise<void> {
      const bundle = await getBundleFn(userId);
      if (!bundle) {
        throw new Error(`User ${userId} has no key bundle — cannot create worker key`);
      }

      // Step 1: unwrap DEK into session-wrapped form (safe over IPC)
      const sessionWrapped = await unwrapFn(sealingKey, bundle.mlkemSealedDk, bundle.wrappedDek);

      // Step 2: re-wrap with the user's own mlkemEk → independent worker blob
      const workerSealed = await rewrapFn(sessionWrapped, bundle.mlkemEk);

      // Zero the intermediate session-wrapped form (T-16-16)
      sessionWrapped.fill(0);

      try {
        // Step 3: persist worker blob
        await pool.query(
          `UPDATE users
           SET worker_sealed_dek = $1, worker_key_enabled = TRUE
           WHERE id = $2`,
          [workerSealed, userId],
        );

        // Step 4: audit (T-16-19)
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
     * Writes an audit_log row (T-16-19).
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
      getUserKeyBundle,
      internalUnwrapSessionDek,
      internalRewrapDek,
    );
  }
  return _workerKeyOps;
}

export async function createWorkerKey(userId: number, sealingKey: Buffer): Promise<void> {
  return getWorkerKeyOps().createWorkerKey(userId, sealingKey);
}

export async function revokeWorkerKey(userId: number): Promise<void> {
  return getWorkerKeyOps().revokeWorkerKey(userId);
}

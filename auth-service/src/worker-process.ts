/**
 * worker-process.ts
 *
 * Background worker process for Phase 16 opt-in background processing (D-17).
 *
 * Runs as a separate Node.js entrypoint: `node dist/worker-process.js`
 *
 * On boot, reads WORKER_PROCESS_ENABLED. If not "1", exits immediately (default mode:
 * user-triggered pipelines only — see D-16).
 *
 * Loop (every 60 seconds):
 *   1. SELECT users WHERE worker_key_enabled = TRUE AND worker_sealed_dek IS NOT NULL
 *   2. For each user, call POST /internal/crypto/unseal-worker-dek to convert the
 *      WORKER_KEY_WRAP_KEY-sealed blob back to a session-wrapped DEK
 *   3. Pass the session-wrapped DEK to FastAPI POST /api/internal/run-pipeline
 *   4. Zero the session-wrapped DEK buffer immediately after the pipeline call
 *
 * Revocation: when a user disables background processing, worker_sealed_dek is set
 * to NULL. The loop checks IS NOT NULL so the user is skipped on the next iteration
 * (within 60 seconds). No explicit revocation signal is needed.
 *
 * Error handling: per-user errors are logged but do not abort the loop. The loop
 * continues processing other users and retries the failed user on the next iteration.
 *
 * Security notes:
 *   - T-16-39: WORKER_KEY_WRAP_KEY is held in process memory. A process memory dump
 *     would expose it. This is the explicit trade-off of "less private, more convenient"
 *     that users accept when enabling background processing (D-17, D-19).
 *   - T-16-44: Users are processed sequentially (not in parallel) to respect the D-09
 *     sub-2-minute per-user pipeline budget and avoid CPU exhaustion.
 *
 * Environment variables:
 *   WORKER_PROCESS_ENABLED      — must be "1" to start the loop
 *   DATABASE_URL / AXIOM_DB_URL — PostgreSQL connection string
 *   INTERNAL_CRYPTO_URL         — default "http://api:8000"; FastAPI base URL
 *   INTERNAL_SERVICE_TOKEN      — shared secret for FastAPI internal endpoints
 */

import pg from 'pg';
import { internalUnsealWorkerDek } from './internal-crypto-client.js';

const { Pool } = pg;

const LOOP_INTERVAL_MS = 60_000; // 60 seconds

// ---------------------------------------------------------------------------
// DB pool singleton
// ---------------------------------------------------------------------------

let _pool: InstanceType<typeof Pool> | null = null;

function getPool(): InstanceType<typeof Pool> {
  if (!_pool) {
    const connStr = process.env.AXIOM_DB_URL ?? process.env.DATABASE_URL;
    if (!connStr) {
      throw new Error('DATABASE_URL or AXIOM_DB_URL must be set for worker process');
    }
    _pool = new Pool({ connectionString: connStr });
  }
  return _pool;
}

// ---------------------------------------------------------------------------
// Graceful shutdown
// ---------------------------------------------------------------------------

let _running = true;

function shutdown(signal: string): void {
  console.log(`[worker] received ${signal}, shutting down gracefully`);
  _running = false;
  getPool().end().catch(() => {});
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

// ---------------------------------------------------------------------------
// Per-user pipeline dispatch
// ---------------------------------------------------------------------------

const API_BASE =
  process.env.INTERNAL_CRYPTO_URL?.replace('/internal/crypto', '') ??
  'http://api:8000';

function getToken(): string {
  const tok = process.env.INTERNAL_SERVICE_TOKEN;
  if (!tok) {
    throw new Error('INTERNAL_SERVICE_TOKEN not configured — worker cannot call FastAPI');
  }
  return tok;
}

/**
 * Dispatch the per-user pipeline for a single user.
 * The session-wrapped DEK is zeroed in the caller immediately after this resolves.
 */
async function dispatchPipeline(userId: number, sessionDekWrapped: Buffer): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/internal/run-pipeline`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Internal-Service-Token': getToken(),
    },
    body: JSON.stringify({
      user_id: userId,
      session_dek_wrapped_hex: sessionDekWrapped.toString('hex'),
    }),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Pipeline dispatch failed for user ${userId}: ${resp.status} ${text}`);
  }
}

// ---------------------------------------------------------------------------
// Main worker loop
// ---------------------------------------------------------------------------

async function runWorkerLoop(): Promise<void> {
  const pool = getPool();
  console.log('[worker] starting background processing loop (interval: 60s)');

  while (_running) {
    try {
      const { rows } = await pool.query<{ id: number; worker_sealed_dek: Buffer }>(
        `SELECT id, worker_sealed_dek
         FROM users
         WHERE worker_key_enabled = TRUE
           AND worker_sealed_dek IS NOT NULL`,
      );

      if (rows.length > 0) {
        console.log(`[worker] processing ${rows.length} user(s) with worker key enabled`);
      }

      // Process users sequentially (T-16-44: avoid CPU exhaustion)
      for (const row of rows) {
        if (!_running) break;
        const userId = row.id;
        let sessionDekWrapped: Buffer | null = null;
        try {
          const sealed = Buffer.from(row.worker_sealed_dek);
          // Convert worker-sealed DEK → session-wrapped DEK via FastAPI IPC
          sessionDekWrapped = await internalUnsealWorkerDek(sealed);
          sealed.fill(0);

          // Hand off to FastAPI pipeline
          await dispatchPipeline(userId, sessionDekWrapped);
          console.log(`[worker] dispatched pipeline for user ${userId}`);
        } catch (err) {
          console.error(`[worker] user ${userId} pipeline failed:`, err);
        } finally {
          // Always zero the session-wrapped DEK (T-16-16)
          if (sessionDekWrapped) {
            sessionDekWrapped.fill(0);
          }
        }
      }
    } catch (err) {
      console.error('[worker] loop error:', err);
    }

    // Sleep for the interval (or until shutdown)
    if (_running) {
      await new Promise<void>((resolve) => {
        const timer = setTimeout(resolve, LOOP_INTERVAL_MS);
        // Allow clean shutdown during sleep
        const check = setInterval(() => {
          if (!_running) {
            clearTimeout(timer);
            clearInterval(check);
            resolve();
          }
        }, 1_000);
        timer.then?.(() => clearInterval(check)); // cleanup if timer resolves first
        // For standard setTimeout (no .then), the check interval handles cleanup
      });
    }
  }

  console.log('[worker] loop exited');
}

// ---------------------------------------------------------------------------
// Entrypoint
// ---------------------------------------------------------------------------

if (process.env.WORKER_PROCESS_ENABLED !== '1') {
  console.log('[worker] WORKER_PROCESS_ENABLED is not set to "1" — exiting (default mode: user-triggered only)');
  process.exit(0);
}

runWorkerLoop().catch((err) => {
  console.error('[worker] fatal error:', err);
  process.exit(1);
});

/**
 * Axiom Auth Service
 *
 * Express microservice using @vitalpoint/near-phantom-auth for:
 * - Passkey (WebAuthn) registration & authentication
 * - Google OAuth
 * - Email magic link authentication
 * - Account recovery (wallet + IPFS)
 * - Session management (HttpOnly cookies)
 *
 * Mounts at /auth via nginx proxy. Shares PostgreSQL with FastAPI.
 */

import express from 'express';
import cors from 'cors';
import cookieParser from 'cookie-parser';
import { createAnonAuth } from '@vitalpoint/near-phantom-auth/server';
import { createMagicLinkRouter } from './magic-link.js';
import { createAxiomUserBridge } from './user-bridge.js';
import { resolveSessionDek, deleteSessionDekCache, deleteSessionClientDekCache } from './key-custody.js';
import { createWorkerKey, revokeWorkerKey } from './worker-key.js';

const app = express();
const PORT = parseInt(process.env.AUTH_PORT || '3100', 10);

// --- Environment ---
const DATABASE_URL = process.env.DATABASE_URL!;
const SESSION_SECRET = process.env.SECRET_KEY || process.env.SESSION_SECRET!;
const RP_ID = process.env.RP_ID || 'localhost';
const RP_NAME = process.env.RP_NAME || 'Axiom';
const ORIGIN = process.env.ORIGIN || 'http://localhost:3003';
const NEAR_NETWORK = (process.env.NEAR_NETWORK || 'mainnet') as 'testnet' | 'mainnet';
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS || ORIGIN).split(',');

// --- Middleware ---
app.use(express.json());
app.use(cookieParser());
app.use(cors({
  origin: ALLOWED_ORIGINS,
  credentials: true,
}));

// Trust proxy (behind nginx)
app.set('trust proxy', 1);

// --- Initialize near-phantom-auth ---
const auth = createAnonAuth({
  nearNetwork: NEAR_NETWORK,
  sessionSecret: SESSION_SECRET,
  sessionDurationMs: 7 * 24 * 60 * 60 * 1000, // 7 days
  database: {
    type: 'postgres',
    connectionString: DATABASE_URL,
  },
  rp: {
    name: RP_NAME,
    id: RP_ID,
    origin: ORIGIN,
  },
  codename: {
    style: 'nato-phonetic',
  },
  oauth: process.env.GOOGLE_CLIENT_ID ? {
    callbackBaseUrl: `${ORIGIN}/auth/oauth/callback`,
    google: {
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    },
  } : undefined,
  recovery: {
    wallet: true,
    ipfs: process.env.PINATA_API_KEY ? {
      pinningService: 'pinata' as const,
      apiKey: process.env.PINATA_API_KEY,
      apiSecret: process.env.PINATA_API_SECRET,
    } : undefined,
  },
  mpc: {
    treasuryAccount: process.env.NEAR_TREASURY_ACCOUNT,
    treasuryPrivateKey: process.env.NEAR_TREASURY_PRIVATE_KEY,
    fundingAmount: process.env.NEAR_FUNDING_AMOUNT || '0.01',
    accountPrefix: 'axiom',
  },
});

// --- Axiom user bridge (maps auth users → Axiom users table) ---
const userBridge = createAxiomUserBridge(DATABASE_URL);

// --- Wrap auth routes with user bridge ---
// After near-phantom-auth creates/authenticates a user, ensure an Axiom user record exists
app.use('/auth', (req, res, next) => {
  // Store original json method to intercept responses
  const originalJson = res.json.bind(res);
  res.json = function(body: unknown) {
    if (res.statusCode >= 200 && res.statusCode < 300 && body && typeof body === 'object') {
      const data = body as Record<string, unknown>;

      // After successful register/login, sync to Axiom users table
      if (data['codename'] || data['nearAccountId'] || data['email']) {
        // Phase 16 (D-11): pass sealing_key_hex through to syncUser for new-user key provisioning
        const syncData: Record<string, unknown> = { ...data };
        if (req.body && typeof req.body === 'object') {
          const body = req.body as Record<string, unknown>;
          if (body['sealingKeyHex']) {
            syncData['sealingKeyHex'] = body['sealingKeyHex'];
          }
        }
        userBridge.syncUser(syncData).catch(err => {
          console.error('Failed to sync Axiom user:', err);
        });
      }

      // Phase 16 (D-26): after login, write session DEK to session_dek_cache
      // The session ID is available in the response body from near-phantom-auth.
      if (data['sessionId'] && req.body && typeof req.body === 'object') {
        const body = req.body as Record<string, unknown>;
        const userId = data['userId'] ?? data['id'];
        const sealingKeyHex = body['sealingKeyHex'] as string | undefined;

        if (sealingKeyHex && userId && typeof userId === 'number') {
          const sessionId = data['sessionId'] as string;
          const sealingKey = Buffer.from(sealingKeyHex, 'hex');
          resolveSessionDek(userId, sessionId, sealingKey)
            .catch(err => {
              console.error('Failed to write session DEK cache:', err);
            })
            .finally(() => {
              sealingKey.fill(0); // zero sealing key after IPC call (T-16-16)
            });
        }
      }

      // Phase 16 (D-26): on logout, delete both session DEK cache tables (T-16-37)
      if (
        req.path === '/logout' &&
        data['success'] === true &&
        req.cookies &&
        typeof req.cookies === 'object'
      ) {
        // Extract session ID from the session cookie (near-phantom-auth sets 'session')
        const sessionId = (req.cookies as Record<string, string>)['session'];
        if (sessionId) {
          // Delete from session_dek_cache (prevents further pipeline requests)
          deleteSessionDekCache(sessionId).catch(err => {
            console.error('Failed to delete session DEK cache on logout:', err);
          });
          // T-16-37: also delete from session_client_dek_cache so accountant
          // viewing sessions are invalidated immediately on logout (plan 16-06 handoff).
          deleteSessionClientDekCache(sessionId).catch((err: Error) => {
            console.error('Failed to delete session_client_dek_cache on logout:', err);
          });
        }
      }
    }
    return originalJson(body);
  };
  next();
});

// --- Mount auth routes ---
// Passkey + session routes: /auth/register/*, /auth/login/*, /auth/session, /auth/logout
app.use('/auth', auth.router);

// OAuth routes: /auth/oauth/*
if (auth.oauthRouter) {
  app.use('/auth/oauth', auth.oauthRouter);
}

// Recovery routes are included in auth.router:
// /auth/recovery/wallet/*, /auth/recovery/ipfs/*

// Magic link routes: /auth/magic-link/*
const magicLinkRouter = createMagicLinkRouter({
  db: auth.db,
  sessionManager: auth.sessionManager,
  mpcManager: auth.mpcManager,
  secretKey: SESSION_SECRET,
  fromEmail: process.env.SES_FROM_EMAIL || 'axiom@vitalpoint.ai',
  sesRegion: process.env.SES_REGION || 'ca-central-1',
  origin: ORIGIN,
});
app.use('/auth/magic-link', magicLinkRouter);

// --- Worker key routes (D-17, plan 16-07) ---

/**
 * POST /auth/worker-key/enable
 *
 * Enable background processing for the authenticated user.
 * Reads the session DEK from session_dek_cache, seals it with WORKER_KEY_WRAP_KEY
 * via FastAPI's /internal/crypto/seal-worker-dek endpoint, and stores the result
 * in users.worker_sealed_dek.
 */
app.post('/auth/worker-key/enable', async (req, res) => {
  try {
    const sessionCookieName = 'session'; // near-phantom-auth sets this
    const sessionId = req.cookies[sessionCookieName] as string | undefined;
    if (!sessionId) {
      return res.status(401).json({ error: 'no session' });
    }

    // Look up the user_id from the sessions table
    const pool = (await import('./key-custody.js')).default;
    // Use the pg Pool directly — import the helper
    const { getUserKeyBundle } = await import('./key-custody.js');
    // We need to query sessions; use the same DATABASE_URL pool
    const pg = await import('pg');
    const sessionPool = new pg.default.Pool({ connectionString: process.env.DATABASE_URL! });
    const { rows } = await sessionPool.query(
      `SELECT user_id FROM session_dek_cache WHERE session_id = $1`,
      [sessionId],
    );
    await sessionPool.end();

    if (rows.length === 0) {
      return res.status(401).json({ error: 'no session DEK — user not logged in with key' });
    }
    const userId = rows[0]['user_id'] as number;

    // createWorkerKey reads session_dek_cache internally
    await createWorkerKey(userId, sessionId);
    return res.json({ enabled: true, status: 'active' });
  } catch (err) {
    console.error('[worker-key] enable failed:', err);
    return res.status(500).json({ error: 'failed to enable worker key' });
  }
});

/**
 * DELETE /auth/worker-key
 *
 * Revoke background processing for the authenticated user.
 * Clears users.worker_sealed_dek and writes an audit row.
 */
app.delete('/auth/worker-key', async (req, res) => {
  try {
    const sessionCookieName = 'session';
    const sessionId = req.cookies[sessionCookieName] as string | undefined;
    if (!sessionId) {
      return res.status(401).json({ error: 'no session' });
    }

    const pg = await import('pg');
    const sessionPool = new pg.default.Pool({ connectionString: process.env.DATABASE_URL! });
    const { rows } = await sessionPool.query(
      `SELECT user_id FROM session_dek_cache WHERE session_id = $1`,
      [sessionId],
    );
    await sessionPool.end();

    if (rows.length === 0) {
      return res.status(401).json({ error: 'no session' });
    }
    const userId = rows[0]['user_id'] as number;

    await revokeWorkerKey(userId);
    return res.json({ enabled: false, status: 'revoked' });
  } catch (err) {
    console.error('[worker-key] revoke failed:', err);
    return res.status(500).json({ error: 'failed to revoke worker key' });
  }
});

// --- Health check ---
app.get('/auth/health', (_req, res) => {
  res.json({ status: 'ok', service: 'auth' });
});

// --- Start ---
async function start() {
  // Initialize database schema (creates near-phantom-auth tables if needed)
  await auth.initialize();

  // Initialize user bridge table
  await userBridge.initialize();

  app.listen(PORT, '0.0.0.0', () => {
    console.log(`Auth service listening on port ${PORT}`);
    console.log(`RP_ID: ${RP_ID}, ORIGIN: ${ORIGIN}`);
    console.log(`NEAR network: ${NEAR_NETWORK}`);
    console.log(`OAuth: ${auth.oauthManager ? 'enabled' : 'disabled'}`);
    console.log(`Recovery wallet: ${auth.walletRecovery ? 'enabled' : 'disabled'}`);
    console.log(`Recovery IPFS: ${auth.ipfsRecovery ? 'enabled' : 'disabled'}`);
  });
}

start().catch(err => {
  console.error('Failed to start auth service:', err);
  process.exit(1);
});

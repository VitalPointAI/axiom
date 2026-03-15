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
    // After successful register/login, sync to Axiom users table
    if (res.statusCode >= 200 && res.statusCode < 300 && body && typeof body === 'object') {
      const data = body as Record<string, unknown>;
      if (data.codename || data.nearAccountId || data.email) {
        userBridge.syncUser(data).catch(err => {
          console.error('Failed to sync Axiom user:', err);
        });
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

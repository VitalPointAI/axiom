/**
 * Magic Link Email Authentication
 *
 * Handles email-based passwordless auth via AWS SES.
 * Integrates with near-phantom-auth's session manager and MPC account system.
 */

import { Router, Request, Response } from 'express';
import crypto from 'crypto';
import { SESClient, SendEmailCommand } from '@aws-sdk/client-ses';
import type { DatabaseAdapter } from '@vitalpoint/near-phantom-auth';
import type { SessionManager, MPCAccountManager } from '@vitalpoint/near-phantom-auth/server';

interface MagicLinkConfig {
  db: DatabaseAdapter;
  sessionManager: SessionManager;
  mpcManager: MPCAccountManager;
  secretKey: string;
  fromEmail: string;
  sesRegion: string;
  origin: string;
}

const TOKEN_EXPIRY_MS = 15 * 60 * 1000; // 15 minutes

export function createMagicLinkRouter(config: MagicLinkConfig): Router {
  const router = Router();
  const ses = new SESClient({ region: config.sesRegion });

  // POST /auth/magic-link/request — send magic link email
  router.post('/request', async (req: Request, res: Response) => {
    try {
      const { email } = req.body;
      if (!email || typeof email !== 'string') {
        res.status(400).json({ error: 'Email is required' });
        return;
      }

      // Generate secure token
      const token = crypto.randomBytes(32).toString('hex');
      const expiresAt = new Date(Date.now() + TOKEN_EXPIRY_MS);

      // Store challenge in near-phantom-auth's challenge table
      await config.db.storeChallenge({
        id: token,
        challenge: email, // Store email as the challenge data
        type: 'recovery', // Reuse recovery type for magic links
        expiresAt,
        metadata: { purpose: 'magic_link', email },
      });

      // Build magic link URL
      const magicUrl = `${config.origin}/auth?token=${encodeURIComponent(token)}`;

      // Send email via SES
      await ses.send(new SendEmailCommand({
        Source: config.fromEmail,
        Destination: { ToAddresses: [email] },
        Message: {
          Subject: { Data: 'Sign in to Axiom' },
          Body: {
            Html: {
              Data: `
                <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto; padding: 32px;">
                  <h2 style="color: #10b981;">Axiom</h2>
                  <p>Click the link below to sign in. This link expires in 15 minutes.</p>
                  <a href="${magicUrl}" style="display: inline-block; background: #10b981; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; font-weight: 600;">
                    Sign In to Axiom
                  </a>
                  <p style="color: #6b7280; font-size: 14px; margin-top: 24px;">
                    If you didn't request this, you can safely ignore this email.
                  </p>
                </div>
              `,
            },
            Text: {
              Data: `Sign in to Axiom: ${magicUrl}\n\nThis link expires in 15 minutes.`,
            },
          },
        },
      }));

      res.json({ sent: true });
    } catch (err) {
      console.error('Magic link request failed:', err);
      // Don't reveal whether email exists
      res.json({ sent: true });
    }
  });

  // GET /auth/magic-link/verify?token=xxx — verify token, create session
  router.get('/verify', async (req: Request, res: Response) => {
    try {
      const { token } = req.query;
      if (!token || typeof token !== 'string') {
        res.status(400).json({ error: 'Token is required' });
        return;
      }

      // Look up challenge
      const challenge = await config.db.getChallenge(token);
      if (!challenge) {
        res.status(401).json({ error: 'Invalid or expired token' });
        return;
      }

      if (new Date() > challenge.expiresAt) {
        await config.db.deleteChallenge(token);
        res.status(401).json({ error: 'Token expired' });
        return;
      }

      const email = (challenge.metadata as Record<string, string>)?.email || challenge.challenge;

      // Consume the token
      await config.db.deleteChallenge(token);

      // Find or create OAuth user by email
      let user = await config.db.getOAuthUserByEmail(email);

      if (!user) {
        // Create MPC account for new user
        const tempId = crypto.randomUUID();
        const mpcAccount = await config.mpcManager.createAccount(tempId);

        user = await config.db.createOAuthUser({
          email,
          nearAccountId: mpcAccount.nearAccountId,
          mpcPublicKey: mpcAccount.mpcPublicKey,
          derivationPath: mpcAccount.derivationPath,
          provider: {
            provider: 'google', // Reuse provider field for email
            providerId: email,
            email,
            connectedAt: new Date(),
          },
        });
      }

      // Create session
      const session = await config.sessionManager.createSession(user.id, res, {
        ipAddress: req.ip,
        userAgent: req.get('user-agent'),
      });

      res.json({
        success: true,
        user: {
          userId: user.id,
          email: user.email,
          nearAccountId: user.nearAccountId,
          codename: null,
          username: null,
          isAdmin: false,
          authMethod: 'email',
        },
        expiresAt: session.expiresAt.toISOString(),
      });
    } catch (err) {
      console.error('Magic link verify failed:', err);
      res.status(401).json({ error: 'Token verification failed' });
    }
  });

  return router;
}

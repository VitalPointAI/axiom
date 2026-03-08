import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { getDb } from '@/lib/db';
import crypto from 'crypto';

const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID;
const GOOGLE_CLIENT_SECRET = process.env.GOOGLE_CLIENT_SECRET;
const REDIRECT_URI = process.env.NEXT_PUBLIC_APP_URL + '/api/phantom-auth/oauth/callback';
const APP_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://neartax.vitalpoint.ai';

interface GoogleTokenResponse {
  access_token: string;
  id_token: string;
  token_type: string;
}

interface GoogleUserInfo {
  sub: string;
  email: string;
  email_verified: boolean;
  name?: string;
  picture?: string;
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const code = searchParams.get('code');
    const state = searchParams.get('state');
    const error = searchParams.get('error');

    if (error) {
      return NextResponse.redirect(`${APP_URL}/auth?error=${encodeURIComponent(error)}`);
    }

    if (!code || !state) {
      return NextResponse.redirect(`${APP_URL}/auth?error=missing_params`);
    }

    // Verify state
    const cookieStore = await cookies();
    const savedState = cookieStore.get('oauth_state')?.value;
    
    if (state !== savedState) {
      return NextResponse.redirect(`${APP_URL}/auth?error=invalid_state`);
    }

    // Clear state cookie
    cookieStore.delete('oauth_state');

    if (!GOOGLE_CLIENT_ID || !GOOGLE_CLIENT_SECRET) {
      return NextResponse.redirect(`${APP_URL}/auth?error=oauth_not_configured`);
    }

    // Exchange code for tokens
    const tokenRes = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        code,
        client_id: GOOGLE_CLIENT_ID,
        client_secret: GOOGLE_CLIENT_SECRET,
        redirect_uri: REDIRECT_URI,
        grant_type: 'authorization_code',
      }),
    });

    if (!tokenRes.ok) {
      console.error('Token exchange failed:', await tokenRes.text());
      return NextResponse.redirect(`${APP_URL}/auth?error=token_exchange_failed`);
    }

    const tokens: GoogleTokenResponse = await tokenRes.json();

    // Get user info
    const userRes = await fetch('https://www.googleapis.com/oauth2/v3/userinfo', {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    });

    if (!userRes.ok) {
      return NextResponse.redirect(`${APP_URL}/auth?error=userinfo_failed`);
    }

    const googleUser: GoogleUserInfo = await userRes.json();

    if (!googleUser.email_verified) {
      return NextResponse.redirect(`${APP_URL}/auth?error=email_not_verified`);
    }

    const db = getDb();

    // Ensure oauth_accounts table exists
    await db.prepare(`
      CREATE TABLE IF NOT EXISTS oauth_accounts (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        provider TEXT NOT NULL,
        provider_account_id TEXT NOT NULL,
        email TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        UNIQUE(provider, provider_account_id)
      )
    `).run();

    // Check if OAuth account already linked
    let oauthAccount = await db.prepare(`
      SELECT oa.*, u.near_account_id, u.codename 
      FROM oauth_accounts oa
      JOIN users u ON oa.user_id = u.id
      WHERE oa.provider = 'google' AND oa.provider_account_id = ?
    `).get(googleUser.sub) as any;

    let userId: number;
    let codename: string;
    let nearAccountId: string;

    if (oauthAccount) {
      // Existing user - sign them in
      userId = oauthAccount.user_id;
      codename = oauthAccount.codename;
      nearAccountId = oauthAccount.near_account_id;
    } else {
      // Check if email is already associated with a user
      let user = await db.prepare('SELECT * FROM users WHERE near_account_id = ?')
        .get(googleUser.email) as any;

      if (!user) {
        // Create new user
        const hash = crypto.createHash('sha256').update(googleUser.sub + 'google').digest('hex');
        nearAccountId = hash.slice(0, 64);
        codename = googleUser.name?.split(' ')[0]?.toLowerCase() || 
                   googleUser.email.split('@')[0].slice(0, 15);

        await db.prepare(`
          INSERT INTO users (near_account_id, codename, created_at, last_login_at)
          VALUES (?, ?, NOW(), NOW())
        `).run(nearAccountId, codename);

        user = await db.prepare('SELECT * FROM users WHERE near_account_id = ?').get(nearAccountId);
      }

      userId = user.id;
      codename = user.codename || googleUser.email.split('@')[0];
      nearAccountId = user.near_account_id;

      // Link OAuth account
      await db.prepare(`
        INSERT INTO oauth_accounts (id, user_id, provider, provider_account_id, email)
        VALUES (?, ?, 'google', ?, ?)
      `).run(crypto.randomUUID(), userId, googleUser.sub, googleUser.email);
    }

    // Create session
    const sessionToken = crypto.randomUUID();
    
    await db.prepare(`
      CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
      )
    `).run();

    await db.prepare(`
      INSERT INTO sessions (id, user_id, expires_at)
      VALUES (?, ?, NOW() + INTERVAL '7 days')
    `).run(sessionToken, userId);

    // Update last login
    await db.prepare('UPDATE users SET last_login_at = datetime("now") WHERE id = ?').run(userId);

    // Set session cookie
    cookieStore.set('neartax_session', sessionToken, {
      httpOnly: true,
      secure: true,
      sameSite: 'lax',
      maxAge: 60 * 60 * 24 * 7,
      path: '/',
    });

    // Redirect to dashboard
    return NextResponse.redirect(`${APP_URL}/dashboard`);
  } catch (error) {
    console.error('OAuth callback error:', error);
    return NextResponse.redirect(`${APP_URL}/auth?error=callback_failed`);
  }
}

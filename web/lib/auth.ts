import { cookies } from 'next/headers';
import { getDb } from './db';

export interface AuthUser {
  userId: number;
  nearAccountId: string;
  codename?: string;
}

export async function getAuthenticatedUser(): Promise<AuthUser | null> {
  const cookieStore = await cookies();
  const sessionToken = cookieStore.get('neartax_session')?.value;
  
  if (!sessionToken) {
    return null;
  }
  
  const db = getDb();
  const session = await db.prepare(`
    SELECT s.user_id, u.near_account_id, u.codename
    FROM sessions s
    JOIN users u ON s.user_id = u.id
    WHERE s.id = ? AND s.expires_at > datetime('now')
  `).get(sessionToken) as { user_id: number; near_account_id: string; codename: string | null } | undefined;
  
  if (!session) {
    return null;
  }
  
  return {
    userId: session.user_id,
    nearAccountId: session.near_account_id,
    codename: session.codename || undefined
  };
}

export async function createSession(userId: number): Promise<string> {
  const { cookies } = await import('next/headers');
  const crypto = await import('crypto');
  const db = getDb();
  
  const sessionToken = crypto.randomBytes(32).toString('hex');
  const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000); // 7 days
  
  await db.prepare(`
    INSERT INTO sessions (id, user_id, expires_at)
    VALUES (?, ?, ?)
  `).run(sessionToken, userId, expiresAt.toISOString());
  
  const cookieStore = await cookies();
  cookieStore.set('neartax_session', sessionToken, {
    httpOnly: true,
    secure: true,
    sameSite: 'lax',
    maxAge: 7 * 24 * 60 * 60,
    path: '/',
  });
  
  return sessionToken;
}

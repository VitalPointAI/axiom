import { cookies } from 'next/headers';
import { getDb } from './db';

export interface AuthUser {
  userId: number;
  nearAccountId: string;
  codename?: string;
  isAdmin?: boolean;
  // Accountant viewing fields
  isViewingAsClient?: boolean;
  viewingClientId?: number;
  viewingClientName?: string;
  actualUserId?: number; // The accountant's real user ID when viewing as client
  permissionLevel?: 'read' | 'readwrite';
}

export async function getAuthenticatedUser(): Promise<AuthUser | null> {
  const cookieStore = await cookies();
  const sessionToken = cookieStore.get('neartax_session')?.value;
  const viewingAsClientId = cookieStore.get('neartax_viewing_as')?.value;
  
  if (!sessionToken) {
    return null;
  }
  
  const db = getDb();
  const session = await db.prepare(`
    SELECT s.user_id, u.near_account_id, u.codename, u.username, u.is_admin
    FROM sessions s
    JOIN users u ON s.user_id = u.id
    WHERE s.id = $1 AND s.expires_at > NOW()
  `).get(sessionToken) as { 
    user_id: number; 
    near_account_id: string; 
    codename: string | null;
    username: string | null;
    is_admin: boolean | null;
  } | undefined;
  
  if (!session) {
    return null;
  }

  // If viewing as a client, verify access and return client's context
  if (viewingAsClientId) {
    const clientId = parseInt(viewingAsClientId, 10);
    
    // Verify accountant has access to this client
    const access = await db.prepare(`
      SELECT aa.permission_level, u.near_account_id, u.codename, u.username
      FROM accountant_access aa
      JOIN users u ON aa.client_user_id = u.id
      WHERE aa.accountant_user_id = $1 AND aa.client_user_id = $2
    `).get(session.user_id, clientId) as {
      permission_level: 'read' | 'readwrite';
      near_account_id: string;
      codename: string | null;
      username: string | null;
    } | undefined;

    if (access) {
      // Update last_accessed_at
      await db.prepare(`
        UPDATE accountant_access 
        SET last_accessed_at = NOW() 
        WHERE accountant_user_id = $1 AND client_user_id = $2
      `).run(session.user_id, clientId);

      return {
        userId: clientId, // Use client's ID for data access
        nearAccountId: access.near_account_id,
        codename: access.codename || undefined,
        isAdmin: false, // Client view is never admin
        isViewingAsClient: true,
        viewingClientId: clientId,
        viewingClientName: access.username || access.codename || access.near_account_id,
        actualUserId: session.user_id, // Accountant's real ID
        permissionLevel: access.permission_level,
      };
    }
    // If access not found, clear the cookie and continue as normal user
  }
  
  return {
    userId: session.user_id,
    nearAccountId: session.near_account_id,
    codename: session.codename || undefined,
    isAdmin: session.is_admin || false,
  };
}

/**
 * Get authenticated user and verify they are an admin.
 * Returns null if not authenticated or not an admin.
 */
export async function getAuthenticatedAdmin(): Promise<AuthUser | null> {
  const user = await getAuthenticatedUser();
  if (!user || !user.isAdmin) {
    return null;
  }
  return user;
}

/**
 * Require admin access - throws standardized error response if not admin.
 * Use in API routes: const admin = await requireAdmin(); if (!admin) return admin;
 */
export async function requireAdmin(): Promise<AuthUser | Response> {
  const user = await getAuthenticatedUser();
  if (!user) {
    return new Response(JSON.stringify({ error: 'Authentication required' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' }
    });
  }
  if (!user.isAdmin) {
    return new Response(JSON.stringify({ error: 'Admin access required' }), {
      status: 403,
      headers: { 'Content-Type': 'application/json' }
    });
  }
  return user;
}

export async function createSession(userId: number): Promise<string> {
  const { cookies } = await import('next/headers');
  const crypto = await import('crypto');
  const db = getDb();
  
  const sessionToken = crypto.randomBytes(32).toString('hex');
  const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000); // 7 days
  
  await db.prepare(`
    INSERT INTO sessions (id, user_id, expires_at)
    VALUES ($1, $2, $3)
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

/**
 * Invalidate all sessions for a user (logout everywhere)
 */
export async function invalidateAllSessions(userId: number): Promise<void> {
  const db = getDb();
  await db.prepare(`
    DELETE FROM sessions WHERE user_id = $1
  `).run(userId);
}

/**
 * Invalidate current session only
 */
export async function invalidateCurrentSession(): Promise<void> {
  const cookieStore = await cookies();
  const sessionToken = cookieStore.get('neartax_session')?.value;
  
  if (sessionToken) {
    const db = getDb();
    await db.prepare(`
      DELETE FROM sessions WHERE id = $1
    `).run(sessionToken);
  }
  
  cookieStore.delete('neartax_session');
}

// Check if current user can write (for readwrite permission check)
export function canWrite(auth: AuthUser): boolean {
  if (!auth.isViewingAsClient) return true; // Own account - full access
  return auth.permissionLevel === 'readwrite';
}

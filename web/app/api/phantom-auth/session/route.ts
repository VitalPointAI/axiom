import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { getDb } from '@/lib/db';

export async function GET() {
  try {
    const cookieStore = await cookies();
    const sessionToken = cookieStore.get('neartax_session')?.value;

    console.log('[Session] Cookie token present:', !!sessionToken);
    console.log('[Session] All cookies:', cookieStore.getAll().map(c => c.name));

    if (!sessionToken) {
      return NextResponse.json({ authenticated: false, user: null });
    }

    const db = getDb();

    // Check if sessions table exists
    const tableExists = await db.prepare(`
      SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename='sessions'
    `).get();

    if (!tableExists) {
      console.log('[Session] Sessions table does not exist');
      return NextResponse.json({ authenticated: false, user: null });
    }

    // Get session with user info including codename
    const session = await db.prepare(`
      SELECT s.*, s.expires_at, u.near_account_id, u.codename, u.created_at
      FROM sessions s
      JOIN users u ON s.user_id = u.id
      WHERE s.id = ? AND s.expires_at > datetime('now')
    `).get(sessionToken) as {
      id: string;
      user_id: number;
      expires_at: string;
      near_account_id: string;
      codename: string | null;
      created_at: string;
    } | undefined;

    if (!session) {
      console.log('[Session] Session not found or expired for token:', sessionToken.substring(0, 8) + '...');
      return NextResponse.json({ authenticated: false, user: null });
    }

    console.log('[Session] Found valid session for user:', session.near_account_id);

    // Return both formats for compatibility
    return NextResponse.json({
      // New format (for AnonAuthProvider)
      authenticated: true,
      codename: session.codename,
      nearAccountId: session.near_account_id,
      expiresAt: session.expires_at,
      createdAt: session.created_at,
      // Old format (for useAuth hook)
      user: {
        nearAccountId: session.near_account_id,
        codename: session.codename,
        createdAt: session.created_at,
      }
    });
  } catch (error) {
    console.error('[Session] Error:', error);
    return NextResponse.json({ authenticated: false, user: null });
  }
}

// POST /logout
export async function POST() {
  try {
    const cookieStore = await cookies();
    const sessionToken = cookieStore.get('neartax_session')?.value;

    if (sessionToken) {
      const db = getDb();
      try {
        await db.prepare('DELETE FROM sessions WHERE id = ?').run(sessionToken);
      } catch (e) {
        // Table might not exist
      }
    }

    cookieStore.delete('neartax_session');

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Logout error:', error);
    return NextResponse.json({ error: 'Logout failed' }, { status: 500 });
  }
}

// For backwards compatibility
export async function DELETE() {
  return POST();
}

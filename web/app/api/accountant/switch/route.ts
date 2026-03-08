import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

// POST /api/accountant/switch - Switch to viewing a client's account
// DELETE /api/accountant/switch - Stop viewing client, return to own account
export async function POST(request: NextRequest) {
  try {
    const cookieStore = await cookies();
    const sessionToken = await cookieStore.get('neartax_session')?.value;
    
    if (!sessionToken) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();
    
    // Get the accountant's actual user ID (not the viewed client)
    const session = await db.prepare(`
      SELECT s.user_id
      FROM sessions s
      WHERE s.id = $1 AND s.expires_at > NOW()
    `).get(sessionToken) as { user_id: number } | undefined;

    if (!session) {
      return NextResponse.json({ error: 'Session expired' }, { status: 401 });
    }

    const { clientId } = await request.json();

    if (!clientId) {
      return NextResponse.json({ error: 'clientId required' }, { status: 400 });
    }

    // Verify accountant has access to this client
    const access = await db.prepare(`
      SELECT aa.permission_level, u.near_account_id, u.username, u.codename
      FROM accountant_access aa
      JOIN users u ON aa.client_user_id = u.id
      WHERE aa.accountant_user_id = $1 AND aa.client_user_id = $2
    `).get(session.user_id, clientId) as {
      permission_level: string;
      near_account_id: string;
      username: string | null;
      codename: string | null;
    } | undefined;

    if (!access) {
      return NextResponse.json({ error: 'Access denied to this client' }, { status: 403 });
    }

    // Set the viewing_as cookie
    cookieStore.set('neartax_viewing_as', clientId.toString(), {
      httpOnly: true,
      secure: true,
      sameSite: 'lax',
      maxAge: 24 * 60 * 60, // 24 hours
      path: '/',
    });

    return NextResponse.json({
      success: true,
      message: 'Now viewing client account',
      client: {
        id: clientId,
        nearAccountId: access.near_account_id,
        name: access.username || access.codename || access.near_account_id,
        permissionLevel: access.permission_level,
      },
    });

  } catch (error) {
    console.error('Switch client error:', error);
    return NextResponse.json({ error: 'Failed to switch client' }, { status: 500 });
  }
}

// DELETE - Stop viewing client, return to own account
export async function DELETE() {
  try {
    const cookieStore = await cookies();
    
    // Clear the viewing_as cookie
    cookieStore.delete('neartax_viewing_as');

    return NextResponse.json({
      success: true,
      message: 'Returned to your own account',
    });

  } catch (error) {
    console.error('Exit client view error:', error);
    return NextResponse.json({ error: 'Failed to exit client view' }, { status: 500 });
  }
}

// GET - Get current viewing status and available clients
export async function GET() {
  try {
    const cookieStore = await cookies();
    const sessionToken = await cookieStore.get('neartax_session')?.value;
    const viewingAsClientId = await cookieStore.get('neartax_viewing_as')?.value;
    
    if (!sessionToken) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();
    
    // Get the user's actual ID from session
    const session = await db.prepare(`
      SELECT s.user_id, u.near_account_id, u.username
      FROM sessions s
      JOIN users u ON s.user_id = u.id
      WHERE s.id = $1 AND s.expires_at > NOW()
    `).get(sessionToken) as { 
      user_id: number;
      near_account_id: string;
      username: string | null;
    } | undefined;

    if (!session) {
      return NextResponse.json({ error: 'Session expired' }, { status: 401 });
    }

    // Get list of clients this user has access to
    const clients = await db.prepare(`
      SELECT 
        aa.client_user_id as id,
        aa.permission_level,
        aa.granted_at,
        aa.last_accessed_at,
        u.near_account_id,
        u.username,
        u.codename,
        (SELECT COUNT(*) FROM wallets WHERE user_id = u.id) as wallet_count
      FROM accountant_access aa
      JOIN users u ON aa.client_user_id = u.id
      WHERE aa.accountant_user_id = $1
      ORDER BY aa.last_accessed_at DESC NULLS LAST, aa.granted_at DESC
    `).all(session.user_id) as any[];

    // Current viewing status
    let currentlyViewing = null;
    if (viewingAsClientId) {
      const clientId = parseInt(viewingAsClientId, 10);
      currentlyViewing = clients.find(c => c.id === clientId) || null;
    }

    return NextResponse.json({
      ownAccount: {
        id: session.user_id,
        nearAccountId: session.near_account_id,
        username: session.username,
      },
      isAccountant: clients.length > 0,
      clients: clients.map(c => ({
        id: c.id,
        nearAccountId: c.near_account_id,
        name: c.username || c.codename || c.near_account_id,
        permissionLevel: c.permission_level,
        walletCount: c.wallet_count,
        lastAccessed: c.last_accessed_at,
      })),
      currentlyViewing,
    });

  } catch (error) {
    console.error('Get viewing status error:', error);
    return NextResponse.json({ error: 'Failed to get status' }, { status: 500 });
  }
}

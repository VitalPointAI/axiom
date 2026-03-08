import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

// GET /api/accountant/access - List who has access to your account OR clients you have access to
export async function GET(request: NextRequest) {
  try {
    const user = await getAuthenticatedUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const view = await searchParams.get('view') || 'granted'; // 'granted' or 'clients'

    const db = getDb();

    if (view === 'clients') {
      // Accountant view: list clients I have access to
      const clients = await db.prepare(`
        SELECT 
          aa.id as access_id,
          aa.permission_level,
          aa.granted_at,
          aa.last_accessed_at,
          u.id as client_id,
          u.username as client_username,
          u.near_account as client_near_account,
          (SELECT COUNT(*) FROM wallets WHERE user_id = u.id) as wallet_count
        FROM accountant_access aa
        JOIN users u ON aa.client_user_id = u.id
        WHERE aa.accountant_user_id = ?
        ORDER BY aa.granted_at DESC
      `).all(user.userId);

      return NextResponse.json({ clients });

    } else {
      // User view: list accountants who have access to my account
      const granted = await db.prepare(`
        SELECT 
          aa.id as access_id,
          aa.permission_level,
          aa.granted_at,
          aa.last_accessed_at,
          u.id as accountant_id,
          u.username as accountant_username,
          u.email as accountant_email
        FROM accountant_access aa
        JOIN users u ON aa.accountant_user_id = u.id
        WHERE aa.client_user_id = ?
        ORDER BY aa.granted_at DESC
      `).all(user.userId);

      return NextResponse.json({ granted });
    }

  } catch (error) {
    console.error('Access list error:', error);
    return NextResponse.json({ error: 'Failed to fetch access list' }, { status: 500 });
  }
}

// DELETE /api/accountant/access?id=xxx - Revoke access
export async function DELETE(request: NextRequest) {
  try {
    const user = await getAuthenticatedUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const accessId = await searchParams.get('id');

    if (!accessId) {
      return NextResponse.json({ error: 'Access ID required' }, { status: 400 });
    }

    const db = getDb();

    // User can revoke access they granted (as client)
    // OR accountant can remove their own access
    const result = await db.prepare(`
      DELETE FROM accountant_access 
      WHERE id = ? AND (client_user_id = ? OR accountant_user_id = ?)
    `).run(accessId, user.userId, user.userId);

    if (result.rowCount === 0) {
      return NextResponse.json({ error: 'Access not found or not authorized' }, { status: 404 });
    }

    return NextResponse.json({ success: true, message: 'Access revoked' });

  } catch (error) {
    console.error('Access revoke error:', error);
    return NextResponse.json({ error: 'Failed to revoke access' }, { status: 500 });
  }
}

// PATCH /api/accountant/access?id=xxx - Update permission level
export async function PATCH(request: NextRequest) {
  try {
    const user = await getAuthenticatedUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const accessId = await searchParams.get('id');
    const { permissionLevel } = await request.json();

    if (!accessId) {
      return NextResponse.json({ error: 'Access ID required' }, { status: 400 });
    }

    if (!['read', 'readwrite'].includes(permissionLevel)) {
      return NextResponse.json({ error: 'Invalid permission level' }, { status: 400 });
    }

    const db = getDb();

    // Only the client (account owner) can change permission level
    const result = await db.prepare(`
      UPDATE accountant_access 
      SET permission_level = ?
      WHERE id = ? AND client_user_id = ?
    `).run(permissionLevel, accessId, user.userId);

    if (result.rowCount === 0) {
      return NextResponse.json({ error: 'Access not found or not authorized' }, { status: 404 });
    }

    return NextResponse.json({ success: true, message: 'Permission updated' });

  } catch (error) {
    console.error('Access update error:', error);
    return NextResponse.json({ error: 'Failed to update permission' }, { status: 500 });
  }
}

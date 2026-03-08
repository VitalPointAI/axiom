import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';

// GET /api/accountant/accept?token=xxx - Verify invite token
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const token = await searchParams.get('token');

    if (!token) {
      return NextResponse.json({ error: 'Token required' }, { status: 400 });
    }

    const db = getDb();

    // Find invite by token
    const invite = await db.prepare(`
      SELECT 
        ai.id,
        ai.email,
        ai.permission_level,
        ai.status,
        ai.message,
        ai.expires_at,
        u.username as client_username,
        u.near_account as client_near_account
      FROM accountant_invites ai
      JOIN users u ON ai.user_id = u.id
      WHERE ai.invite_token = ?
    `).get(token) as any;

    if (!invite) {
      return NextResponse.json({ error: 'Invalid invitation token' }, { status: 404 });
    }

    if (invite.status !== 'pending') {
      return NextResponse.json({ 
        error: `Invitation has been ${invite.status}`,
        status: invite.status 
      }, { status: 400 });
    }

    if (new Date(invite.expires_at) < new Date()) {
      // Mark as expired
      await db.prepare(`UPDATE accountant_invites SET status = 'expired' WHERE id = ?`).run(invite.id);
      return NextResponse.json({ error: 'Invitation has expired' }, { status: 400 });
    }

    return NextResponse.json({
      valid: true,
      email: invite.email,
      permissionLevel: invite.permission_level,
      clientName: invite.client_username || invite.client_near_account,
      message: invite.message,
      expiresAt: invite.expires_at,
    });

  } catch (error) {
    console.error('Invite verify error:', error);
    return NextResponse.json({ error: 'Failed to verify invitation' }, { status: 500 });
  }
}

// POST /api/accountant/accept - Accept invitation (requires auth)
export async function POST(request: NextRequest) {
  try {
    const user = await getAuthenticatedUser();
    if (!user) {
      return NextResponse.json({ error: 'Please sign in to accept this invitation' }, { status: 401 });
    }

    const { token } = await request.json();

    if (!token) {
      return NextResponse.json({ error: 'Token required' }, { status: 400 });
    }

    const db = getDb();

    // Find and validate invite
    const invite = await db.prepare(`
      SELECT id, user_id, email, permission_level, status, expires_at
      FROM accountant_invites 
      WHERE invite_token = ?
    `).get(token) as any;

    if (!invite) {
      return NextResponse.json({ error: 'Invalid invitation token' }, { status: 404 });
    }

    if (invite.status !== 'pending') {
      return NextResponse.json({ error: `Invitation has been ${invite.status}` }, { status: 400 });
    }

    if (new Date(invite.expires_at) < new Date()) {
      await db.prepare(`UPDATE accountant_invites SET status = 'expired' WHERE id = ?`).run(invite.id);
      return NextResponse.json({ error: 'Invitation has expired' }, { status: 400 });
    }

    // Cannot accept your own invite
    if (invite.user_id === user.userId) {
      return NextResponse.json({ error: 'Cannot accept your own invitation' }, { status: 400 });
    }

    // Check if access already exists
    const existingAccess = await db.prepare(`
      SELECT id FROM accountant_access 
      WHERE accountant_user_id = ? AND client_user_id = ?
    `).get(user.userId, invite.user_id);

    if (existingAccess) {
      return NextResponse.json({ error: 'You already have access to this account' }, { status: 409 });
    }

    // Create access grant
    await db.prepare(`
      INSERT INTO accountant_access 
      (accountant_user_id, client_user_id, permission_level, granted_via_invite_id)
      VALUES (?, ?, ?, ?)
    `).run(user.userId, invite.user_id, invite.permission_level, invite.id);

    // Mark invite as accepted
    await db.prepare(`
      UPDATE accountant_invites 
      SET status = 'accepted', accepted_at = NOW(), accepted_by_user_id = ?
      WHERE id = ?
    `).run(user.userId, invite.id);

    // Get client info for response
    const client = await db.prepare(`
      SELECT username, near_account FROM users WHERE id = ?
    `).get(invite.user_id) as any;

    return NextResponse.json({
      success: true,
      message: 'Invitation accepted successfully',
      client: {
        username: client?.username,
        nearAccount: client?.near_account,
      },
      permissionLevel: invite.permission_level,
    });

  } catch (error) {
    console.error('Invite accept error:', error);
    return NextResponse.json({ error: 'Failed to accept invitation' }, { status: 500 });
  }
}

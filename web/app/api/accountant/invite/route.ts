import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { getAuthenticatedUser } from '@/lib/auth';
import { randomBytes } from 'crypto';
import { sendAccountantInviteEmail } from '@/lib/email';

// POST /api/accountant/invite - Send invitation to accountant
export async function POST(request: NextRequest) {
  try {
    const user = await getAuthenticatedUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { email, permissionLevel, message } = await request.json();

    if (!email || !email.includes('@')) {
      return NextResponse.json({ error: 'Valid email required' }, { status: 400 });
    }

    if (!['read', 'readwrite'].includes(permissionLevel)) {
      return NextResponse.json({ error: 'Invalid permission level' }, { status: 400 });
    }

    const db = getDb();

    // Check if there's already a pending invite for this email from this user
    const existing = await db.prepare(`
      SELECT id FROM accountant_invites 
      WHERE user_id = ? AND email = ? AND status = 'pending'
    `).get(user.userId, email.toLowerCase());

    if (existing) {
      return NextResponse.json({ 
        error: 'Pending invitation already exists for this email' 
      }, { status: 409 });
    }

    // Generate invite token
    const inviteToken = randomBytes(32).toString('hex');
    
    // Set expiration to 7 days from now
    const expiresAt = new Date();
    expiresAt.setDate(expiresAt.getDate() + 7);

    // Create invite
    const result = await db.prepare(`
      INSERT INTO accountant_invites 
      (user_id, email, permission_level, invite_token, message, expires_at)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(
      user.userId,
      email.toLowerCase(),
      permissionLevel,
      inviteToken,
      message || null,
      expiresAt.toISOString()
    );

    // Get user's name/account for the email
    const userInfo = await db.prepare(`
      SELECT username, near_account FROM users WHERE id = ?
    `).get(user.userId) as { username: string; near_account: string } | undefined;

    const inviteUrl = `${process.env.NEXT_PUBLIC_APP_URL || 'http://157.90.122.69:3003'}/accountant/accept?token=${inviteToken}`;

    // Send email via AWS SES
    const inviterName = userInfo?.username || userInfo?.near_account || 'A NearTax user';
    
    let emailSent = false;
    try {
      emailSent = await sendAccountantInviteEmail({
        toEmail: email.toLowerCase(),
        inviterName,
        inviteUrl,
        permissionLevel,
        personalMessage: message || undefined,
      });
    } catch (emailError) {
      console.error('[Accountant Invite] Email send error:', emailError);
    }

    console.log(`[Accountant Invite] Email ${emailSent ? 'sent' : 'failed'} to ${email}`);

    return NextResponse.json({
      success: true,
      inviteId: result.lastInsertRowid || 0,
      inviteUrl, // Include URL as backup if email fails
      emailSent,
      message: emailSent 
        ? `Invitation sent to ${email}` 
        : `Invitation created. Email delivery failed - please share the link manually.`,
      expiresAt: expiresAt.toISOString(),
    });

  } catch (error) {
    console.error('Accountant invite error:', error);
    return NextResponse.json({ error: 'Failed to send invitation' }, { status: 500 });
  }
}

// GET /api/accountant/invite - List user's sent invitations
export async function GET(request: NextRequest) {
  try {
    const user = await getAuthenticatedUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const db = getDb();

    // Get all invites sent by this user
    const invites = await db.prepare(`
      SELECT 
        ai.id,
        ai.email,
        ai.permission_level,
        ai.status,
        ai.message,
        ai.created_at,
        ai.expires_at,
        ai.accepted_at,
        u.username as accepted_by_username
      FROM accountant_invites ai
      LEFT JOIN users u ON ai.accepted_by_user_id = u.id
      WHERE ai.user_id = ?
      ORDER BY ai.created_at DESC
    `).all(user.userId);

    // Update expired invites
    await db.prepare(`
      UPDATE accountant_invites 
      SET status = 'expired' 
      WHERE user_id = ? AND status = 'pending' AND expires_at < NOW()
    `).run(user.userId);

    return NextResponse.json({ invites });

  } catch (error) {
    console.error('Accountant invites fetch error:', error);
    return NextResponse.json({ error: 'Failed to fetch invitations' }, { status: 500 });
  }
}

// DELETE /api/accountant/invite - Revoke/cancel an invitation
export async function DELETE(request: NextRequest) {
  try {
    const user = await getAuthenticatedUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const inviteId = await searchParams.get('id');

    if (!inviteId) {
      return NextResponse.json({ error: 'Invite ID required' }, { status: 400 });
    }

    const db = getDb();

    // Verify ownership and revoke
    const result = await db.prepare(`
      UPDATE accountant_invites 
      SET status = 'revoked' 
      WHERE id = ? AND user_id = ? AND status = 'pending'
    `).run(inviteId, user.userId);

    if (result.rowCount === 0) {
      return NextResponse.json({ error: 'Invitation not found or already processed' }, { status: 404 });
    }

    return NextResponse.json({ success: true, message: 'Invitation revoked' });

  } catch (error) {
    console.error('Accountant invite revoke error:', error);
    return NextResponse.json({ error: 'Failed to revoke invitation' }, { status: 500 });
  }
}

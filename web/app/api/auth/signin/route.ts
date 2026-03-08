import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function POST(request: NextRequest) {
  try {
    const { nearAccountId } = await request.json();

    if (!nearAccountId || typeof nearAccountId !== 'string') {
      return NextResponse.json(
        { error: 'Invalid NEAR account ID' },
        { status: 400 }
      );
    }

    const db = getDb();

    // Upsert user
    await db.prepare(`
      INSERT INTO users (near_account_id, last_login_at)
      VALUES (?, NOW())
      ON CONFLICT(near_account_id) DO UPDATE SET
        last_login_at = NOW()
    `).run(nearAccountId);

    // Get user data
    const user = await db.prepare(`
      SELECT near_account_id, created_at
      FROM users
      WHERE near_account_id = ?
    `).get(nearAccountId) as { near_account_id: string; created_at: string };

    // Set session cookie (using account ID as simple token for now)
    const cookieStore = await cookies();
    cookieStore.set('neartax_session', nearAccountId, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 60 * 60 * 24 * 7, // 7 days
      path: '/',
    });

    return NextResponse.json({
      user: {
        nearAccountId: user.near_account_id,
        createdAt: user.created_at,
      }
    });
  } catch (error) {
    console.error('Sign in error:', error);
    return NextResponse.json(
      { error: 'Sign in failed' },
      { status: 500 }
    );
  }
}

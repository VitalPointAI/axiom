import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET() {
  try {
    const cookieStore = await cookies();
    const sessionToken = cookieStore.get('neartax_session')?.value;

    if (!sessionToken) {
      return NextResponse.json({ user: null });
    }

    const db = getDb();
    const user = await db.prepare(`
      SELECT near_account_id, created_at 
      FROM users 
      WHERE near_account_id = ?
    `).get(sessionToken) as { near_account_id: string; created_at: string } | undefined;

    if (!user) {
      return NextResponse.json({ user: null });
    }

    return NextResponse.json({
      user: {
        nearAccountId: user.near_account_id,
        createdAt: user.created_at,
      }
    });
  } catch (error) {
    console.error('Session check error:', error);
    return NextResponse.json({ user: null });
  }
}

import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { getDb } from '@/lib/db';

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

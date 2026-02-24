import { cookies } from 'next/headers';
import { NextResponse } from 'next/server';

export async function POST() {
  try {
    const cookieStore = await cookies();
    cookieStore.delete('neartax_session');
    
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Sign out error:', error);
    return NextResponse.json(
      { error: 'Sign out failed' },
      { status: 500 }
    );
  }
}

import { NextRequest, NextResponse } from 'next/server';
import crypto from 'crypto';
import { cookies } from 'next/headers';

const GOOGLE_CLIENT_ID = process.env.GOOGLE_CLIENT_ID;
const REDIRECT_URI = process.env.NEXT_PUBLIC_APP_URL + '/api/phantom-auth/oauth/callback';

export async function POST(request: NextRequest) {
  try {
    const { provider } = await request.json();

    if (provider !== 'google') {
      return NextResponse.json({ error: 'Unsupported provider' }, { status: 400 });
    }

    if (!GOOGLE_CLIENT_ID) {
      return NextResponse.json({ error: 'Google OAuth not configured' }, { status: 500 });
    }

    // Generate state for CSRF protection
    const state = crypto.randomUUID();
    
    // Store state in cookie
    const cookieStore = await cookies();
    cookieStore.set('oauth_state', state, {
      httpOnly: true,
      secure: true,
      sameSite: 'lax',
      maxAge: 60 * 10, // 10 minutes
      path: '/',
    });

    // Build Google OAuth URL
    const params = new URLSearchParams({
      client_id: GOOGLE_CLIENT_ID,
      redirect_uri: REDIRECT_URI,
      response_type: 'code',
      scope: 'openid email profile',
      state,
      access_type: 'offline',
      prompt: 'consent',
    });

    const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?${params}`;

    return NextResponse.json({ authUrl });
  } catch (error) {
    console.error('OAuth start error:', error);
    return NextResponse.json({ error: 'Failed to start OAuth' }, { status: 500 });
  }
}

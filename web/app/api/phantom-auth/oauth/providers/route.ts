import { NextResponse } from 'next/server';

export async function GET() {
  // Return empty providers for now - OAuth not configured
  // To enable Google OAuth, set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET env vars
  const providers = [];

  if (process.env.GOOGLE_CLIENT_ID) {
    providers.push({
      name: 'google',
      authUrl: '/api/phantom-auth/oauth/start?provider=google'
    });
  }

  return NextResponse.json({ providers });
}

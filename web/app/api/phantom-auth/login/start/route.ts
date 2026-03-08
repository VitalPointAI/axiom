import { NextRequest, NextResponse } from 'next/server';
import { createAuthenticationOptions } from '@vitalpoint/near-phantom-auth/webauthn';
import { getDb } from '@/lib/db';
import { loginChallenges } from '@/lib/passkey-challenges';

const RP_ID = process.env.NEXT_PUBLIC_RP_ID || 'neartax.vitalpoint.ai';

export async function POST(request: NextRequest) {
  try {
    const { username } = await request.json();
    
    const db = getDb();
    const user = await db.prepare('SELECT passkey_credential_id FROM users WHERE username = ?').get(username) as any;
    
    if (!user || !user.passkey_credential_id) {
      return NextResponse.json({ error: 'User not found' }, { status: 404 });
    }
    
    const { options, challenge } = await createAuthenticationOptions({
      rpId: RP_ID,
      allowCredentials: [{
        id: user.passkey_credential_id,
      }],
    });
    
    // Store challenge with expiration
    const challengeId = crypto.randomUUID();
    loginChallenges.set(challengeId, {
      challenge,
      username,
      expires: Date.now() + 60000,
    });
    
    return NextResponse.json({ challengeId, options });
  } catch (error: any) {
    console.error('Login start error:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

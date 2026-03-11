import { NextRequest, NextResponse } from 'next/server';
import { createRegistrationOptions } from '@vitalpoint/near-phantom-auth/webauthn';
import { getDb } from '@/lib/db';
import { registerChallenges } from '@/lib/passkey-challenges';

const RP_ID = process.env.NEXT_PUBLIC_RP_ID || 'neartax.vitalpoint.ai';
const RP_NAME = process.env.RP_NAME || 'Axiom';

export async function POST(request: NextRequest) {
  try {
    const { username, email } = await request.json();
    
    if (!username || username.length < 3) {
      return NextResponse.json({ error: 'Username must be at least 3 characters' }, { status: 400 });
    }
    
    const db = getDb();
    const existing = await db.prepare('SELECT id FROM users WHERE near_account_id = ?').get(username);
    if (existing) {
      return NextResponse.json({ error: 'Username already taken' }, { status: 409 });
    }
    
    const { options, challenge } = await createRegistrationOptions({
      rpName: RP_NAME,
      rpId: RP_ID,
      userName: username,
      userDisplayName: username,
    });
    
    // Store challenge with metadata
    const challengeId = crypto.randomUUID();
    registerChallenges.set(challengeId, {
      challenge,
      username,
      email,
      expires: Date.now() + 60000,
    });
    
    return NextResponse.json({ challengeId, options });
  } catch (error: any) {
    console.error('Register start error:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

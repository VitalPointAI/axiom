import { NextRequest, NextResponse } from 'next/server';
import { verifyAuthentication } from '@vitalpoint/near-phantom-auth/webauthn';
import { createSession } from '@/lib/auth';
import { getDb } from '@/lib/db';
import { loginChallenges } from '@/lib/passkey-challenges';

const RP_ID = process.env.NEXT_PUBLIC_RP_ID || 'neartax.vitalpoint.ai';
const ORIGIN = process.env.NEXT_PUBLIC_ORIGIN || 'https://neartax.vitalpoint.ai';

export async function POST(request: NextRequest) {
  try {
    const { challengeId, credential } = await request.json();
    
    const challengeData = loginChallenges.get(challengeId);
    if (!challengeData) {
      return NextResponse.json({ error: 'Challenge not found or expired' }, { status: 400 });
    }
    
    if (challengeData.expires < Date.now()) {
      loginChallenges.delete(challengeId);
      return NextResponse.json({ error: 'Challenge expired' }, { status: 400 });
    }
    
    const db = getDb();
    const user = await db.prepare('SELECT * FROM users WHERE passkey_credential_id = ?').get(credential.id) as any;
    
    if (!user) {
      return NextResponse.json({ error: 'Passkey not found' }, { status: 404 });
    }
    
    // Verify with full cryptographic verification + counter check
    const result = await verifyAuthentication({
      response: credential,
      expectedChallenge: challengeData.challenge,
      expectedOrigin: ORIGIN,
      expectedRPID: RP_ID,
      credential: {
        id: user.passkey_credential_id,
        publicKey: new Uint8Array(Buffer.from(user.passkey_public_key, 'base64')),
        counter: user.passkey_counter || 0,
      },
    });
    
    if (!result.verified) {
      loginChallenges.delete(challengeId);
      return NextResponse.json({ error: result.error || 'Verification failed' }, { status: 401 });
    }
    
    // Update counter to prevent replay attacks
    if (result.newCounter !== undefined) {
      await db.prepare('UPDATE users SET passkey_counter = ? WHERE id = ?').run(result.newCounter, user.id);
    }
    
    // Create session
    await createSession(user.id);
    
    // Clean up challenge
    loginChallenges.delete(challengeId);
    
    return NextResponse.json({ 
      success: true,
      user: {
        id: user.id,
        username: user.username,
        displayName: user.display_name,
        isAdmin: !!user.is_admin,
      }
    });
  } catch (error: any) {
    console.error('Login finish error:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

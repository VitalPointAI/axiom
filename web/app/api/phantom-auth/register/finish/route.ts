import { NextRequest, NextResponse } from 'next/server';
import { verifyRegistration } from '@vitalpoint/near-phantom-auth/webauthn';
import { createSession } from '@/lib/auth';
import { getDb } from '@/lib/db';
import { registerChallenges } from '@/lib/passkey-challenges';

const RP_ID = process.env.NEXT_PUBLIC_RP_ID || 'neartax.vitalpoint.ai';
const ORIGIN = process.env.NEXT_PUBLIC_ORIGIN || 'https://neartax.vitalpoint.ai';

export async function POST(request: NextRequest) {
  try {
    const { challengeId, credential } = await request.json();
    
    const challengeData = registerChallenges.get(challengeId);
    if (!challengeData) {
      return NextResponse.json({ error: 'Challenge not found or expired' }, { status: 400 });
    }
    
    if (challengeData.expires < Date.now()) {
      registerChallenges.delete(challengeId);
      return NextResponse.json({ error: 'Challenge expired' }, { status: 400 });
    }
    
    // Verify with full cryptographic verification
    const result = await verifyRegistration({
      response: credential,
      expectedChallenge: challengeData.challenge,
      expectedOrigin: ORIGIN,
      expectedRPID: RP_ID,
    });
    
    if (!result.verified || !result.credential) {
      registerChallenges.delete(challengeId);
      return NextResponse.json({ error: result.error || 'Verification failed' }, { status: 401 });
    }
    
    // Clean up challenge
    registerChallenges.delete(challengeId);
    
    // Create user
    const db = getDb();
    const insertResult = await db.prepare(`
      INSERT INTO users (username, email, display_name, passkey_credential_id, passkey_public_key, passkey_counter)
      VALUES (?, ?, ?, ?, ?, ?)
    `).run(
      challengeData.username,
      challengeData.email || null,
      challengeData.username,
      result.credential.id,
      Buffer.from(result.credential.publicKey).toString('base64'),
      result.credential.counter
    );
    
    const userId = insertResult.lastInsertRowid as number;
    
    // Create session
    await createSession(userId);
    
    return NextResponse.json({ 
      success: true,
      user: {
        id: userId,
        username: challengeData.username,
      }
    });
  } catch (error: any) {
    console.error('Register finish error:', error);
    if (error.message?.includes('UNIQUE constraint')) {
      return NextResponse.json({ error: 'Username already taken' }, { status: 409 });
    }
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

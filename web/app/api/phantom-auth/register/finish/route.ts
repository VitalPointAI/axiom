import { NextRequest, NextResponse } from 'next/server';
import { verifyRegistration } from '@vitalpoint/near-phantom-auth/webauthn';
import { createSession } from '@/lib/auth';
import { getDb } from '@/lib/db';
import { registerChallenges } from '@/lib/passkey-challenges';

const RP_ID = process.env.NEXT_PUBLIC_RP_ID || 'neartax.vitalpoint.ai';
const ORIGIN = process.env.NEXT_PUBLIC_ORIGIN || 'https://neartax.vitalpoint.ai';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    
    // Client sends 'response', but we also support 'credential' for backwards compatibility
    const { challengeId, response, credential, username } = body;
    const passkeyResponse = response || credential;
    
    console.log('[Register] challengeId:', challengeId);
    console.log('[Register] username from body:', username);
    console.log('[Register] has response:', !!passkeyResponse);
    
    const challengeData = registerChallenges.get(challengeId);
    if (!challengeData) {
      console.log('[Register] Challenge not found');
      return NextResponse.json({ error: 'Challenge not found or expired' }, { status: 400 });
    }
    
    if (challengeData.expires < Date.now()) {
      console.log('[Register] Challenge expired');
      registerChallenges.delete(challengeId);
      return NextResponse.json({ error: 'Challenge expired' }, { status: 400 });
    }
    
    // Use username from body or from challenge data
    const finalUsername = username || challengeData.username;
    console.log('[Register] Final username:', finalUsername);
    
    // Verify with full cryptographic verification
    const result = await verifyRegistration({
      response: passkeyResponse,
      expectedChallenge: challengeData.challenge,
      expectedOrigin: ORIGIN,
      expectedRPID: RP_ID,
    });
    
    console.log('[Register] Verification result:', JSON.stringify({ 
      verified: result.verified, 
      error: result.error, 
      hasCredential: !!result.credential,
    }));
    
    if (!result.verified || !result.credential) {
      registerChallenges.delete(challengeId);
      console.log('[Register] Verification failed:', result.error);
      return NextResponse.json({ error: result.error || 'Verification failed' }, { status: 401 });
    }
    
    // Clean up challenge
    registerChallenges.delete(challengeId);
    
    const db = getDb();
    
    console.log('[Register] Creating user:', finalUsername);
    
    // Create user
    const userResult = await db.prepare(`
      INSERT INTO users (near_account_id, created_at)
      VALUES (?, NOW())
      RETURNING id
    `).get(finalUsername) as { id: number };
    
    const userId = userResult.id;
    console.log('[Register] Created user with ID:', userId);
    
    // Create passkey
    const passkeyId = crypto.randomUUID();
    await db.prepare(`
      INSERT INTO passkeys (id, user_id, credential_id, public_key, counter, created_at)
      VALUES (?, ?, ?, ?, ?, NOW())
    `).run(
      passkeyId,
      userId,
      result.credential.id,
      result.credential.publicKey,
      result.credential.counter
    );
    console.log('[Register] Created passkey');
    
    // Create session
    await createSession(userId);
    console.log('[Register] Created session');
    
    return NextResponse.json({ 
      success: true,
      user: {
        id: userId,
        username: finalUsername,
      }
    });
  } catch (error: any) {
    console.error('[Register] Error:', error);
    if (error.message?.includes('duplicate key') || error.message?.includes('unique')) {
      return NextResponse.json({ error: 'Username already taken' }, { status: 409 });
    }
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

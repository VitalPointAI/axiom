import { NextRequest, NextResponse } from 'next/server';
import { verifyAuthentication } from '@vitalpoint/near-phantom-auth/webauthn';
import { createSession } from '@/lib/auth';
import { getDb } from '@/lib/db';
import { loginChallenges } from '@/lib/passkey-challenges';

const RP_ID = process.env.NEXT_PUBLIC_RP_ID || 'neartax.vitalpoint.ai';
const ORIGIN = process.env.NEXT_PUBLIC_ORIGIN || 'https://neartax.vitalpoint.ai';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { challengeId } = body;
    // Accept both 'credential' and 'response' for library compatibility
    const credential = body.credential || body.response;
    
    console.log('[Login Finish] challengeId:', challengeId);
    console.log('[Login Finish] credential id:', credential?.id);
    
    const challengeData = loginChallenges.get(challengeId);
    if (!challengeData) {
      return NextResponse.json({ error: 'Challenge not found or expired' }, { status: 400 });
    }
    
    if (challengeData.expires < Date.now()) {
      loginChallenges.delete(challengeId);
      return NextResponse.json({ error: 'Challenge expired' }, { status: 400 });
    }
    
    const db = getDb();
    
    // Get passkey and user info
    const passkey = await db.prepare(`
      SELECT p.*, u.id as user_id, u.near_account_id, u.codename
      FROM passkeys p
      JOIN users u ON u.id = p.user_id
      WHERE p.credential_id = ?
    `).get(credential.id) as any;
    
    console.log('[Login Finish] Passkey found:', !!passkey);
    
    if (!passkey) {
      return NextResponse.json({ error: 'Passkey not found' }, { status: 404 });
    }
    
    // Verify with full cryptographic verification + counter check
    const result = await verifyAuthentication({
      response: credential,
      expectedChallenge: challengeData.challenge,
      expectedOrigin: ORIGIN,
      expectedRPID: RP_ID,
      credential: {
        id: passkey.credential_id,
        publicKey: passkey.public_key,
        counter: passkey.counter || 0,
      },
    });
    
    console.log('[Login Finish] Verification result:', result.verified, result.error);
    
    if (!result.verified) {
      loginChallenges.delete(challengeId);
      return NextResponse.json({ error: result.error || 'Verification failed' }, { status: 401 });
    }
    
    // Update counter to prevent replay attacks
    if (result.newCounter !== undefined) {
      await db.prepare('UPDATE passkeys SET counter = ?, last_used_at = NOW() WHERE id = ?').run(result.newCounter, passkey.id);
    }
    
    // Create session
    await createSession(passkey.user_id);
    console.log('[Login Finish] Session created for user:', passkey.user_id);
    
    // Clean up challenge
    loginChallenges.delete(challengeId);
    
    return NextResponse.json({ 
      success: true,
      codename: passkey.codename || passkey.near_account_id,
      user: {
        id: passkey.user_id,
        username: passkey.near_account_id,
        displayName: passkey.codename || passkey.near_account_id,
      }
    });
  } catch (error: any) {
    console.error('[Login Finish] Error:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

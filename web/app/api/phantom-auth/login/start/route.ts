import { NextRequest, NextResponse } from 'next/server';
import { createAuthenticationOptions } from '@vitalpoint/near-phantom-auth/webauthn';
import { getDb } from '@/lib/db';
import { loginChallenges } from '@/lib/passkey-challenges';

const RP_ID = process.env.NEXT_PUBLIC_RP_ID || 'neartax.vitalpoint.ai';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    // Accept both 'username' and 'codename' for compatibility with library
    const username = body.username || body.codename;
    console.log('[Login Start] Username:', username);
    
    let allowCredentials: Array<{ id: string }> | undefined;
    
    if (username) {
      // Username provided - look up their specific credential
      const db = getDb();
      const user = await db.prepare(`
        SELECT u.id, p.credential_id 
        FROM users u
        JOIN passkeys p ON p.user_id = u.id
        WHERE u.near_account_id = ?
        LIMIT 1
      `).get(username) as { id: number; credential_id: string } | undefined;
      
      console.log('[Login Start] User found:', user);
      
      if (!user || !user.credential_id) {
        console.log('[Login Start] User not found or no credential');
        return NextResponse.json({ error: 'User not found' }, { status: 404 });
      }
      
      allowCredentials = [{ id: user.credential_id }];
    } else {
      // No username - discoverable credential flow (passkey knows who user is)
      console.log('[Login Start] Discoverable credential flow (no username)');
      allowCredentials = undefined;
    }
    
    const { options, challenge } = await createAuthenticationOptions({
      rpId: RP_ID,
      allowCredentials,
    });
    
    // Store challenge with expiration
    const challengeId = crypto.randomUUID();
    loginChallenges.set(challengeId, {
      challenge,
      username,
      expires: Date.now() + 60000,
    });
    
    console.log('[Login Start] Challenge created:', challengeId);
    return NextResponse.json({ challengeId, options });
  } catch (error: any) {
    console.error('[Login Start] Error:', error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}

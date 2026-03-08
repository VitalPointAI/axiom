/**
 * Shared challenge storage for WebAuthn flows
 * Uses global to persist across hot reloads in development
 * For production with multiple instances, use Redis or DB
 */

interface ChallengeData {
  challenge: string;
  username?: string;
  email?: string;
  expires: number;
}

// Use global to persist across module reloads
const globalChallenges = globalThis as typeof globalThis & {
  __passkeyRegisterChallenges?: Map<string, ChallengeData>;
  __passkeyLoginChallenges?: Map<string, ChallengeData>;
};

if (!globalChallenges.__passkeyRegisterChallenges) {
  globalChallenges.__passkeyRegisterChallenges = new Map();
}

if (!globalChallenges.__passkeyLoginChallenges) {
  globalChallenges.__passkeyLoginChallenges = new Map();
}

export const registerChallenges = globalChallenges.__passkeyRegisterChallenges;
export const loginChallenges = globalChallenges.__passkeyLoginChallenges;

// Clean expired challenges
export function cleanExpiredChallenges() {
  const now = Date.now();
  for (const [id, data] of registerChallenges) {
    if (data.expires < now) registerChallenges.delete(id);
  }
  for (const [id, data] of loginChallenges) {
    if (data.expires < now) loginChallenges.delete(id);
  }
}

// Run cleanup every minute
if (typeof setInterval !== 'undefined') {
  setInterval(cleanExpiredChallenges, 60000);
}

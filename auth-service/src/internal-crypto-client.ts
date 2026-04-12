/**
 * internal-crypto-client.ts
 *
 * Typed fetch wrapper for the FastAPI internal crypto router (D-27).
 *
 * auth-service delegates ALL ML-KEM-768 operations to FastAPI via loopback IPC.
 * This module provides the three typed wrappers that call:
 *   POST /internal/crypto/keygen
 *   POST /internal/crypto/unwrap-session-dek
 *   POST /internal/crypto/rewrap-dek
 *
 * Security controls:
 *   - INTERNAL_SERVICE_TOKEN must be set; throws (fail-closed) if missing.
 *   - X-Internal-Service-Token header is sent with every request.
 *   - sealing_key size validation before network call.
 *
 * Environment variables:
 *   INTERNAL_CRYPTO_URL     — default "http://api:8000"; use "http://localhost:8000" for local dev
 *   INTERNAL_SERVICE_TOKEN  — shared secret matching FastAPI INTERNAL_SERVICE_TOKEN
 */

const INTERNAL_CRYPTO_URL =
  process.env.INTERNAL_CRYPTO_URL ?? 'http://api:8000';

/**
 * Returns the shared internal service token or throws if not configured.
 * Fail-closed: auth-service must not silently skip the token check.
 */
function getToken(): string {
  const tok = process.env.INTERNAL_SERVICE_TOKEN;
  if (!tok) {
    throw new Error(
      'INTERNAL_SERVICE_TOKEN not configured — auth-service cannot call FastAPI internal crypto',
    );
  }
  return tok;
}

/**
 * POST to an internal crypto endpoint with the service token header.
 * Throws on any non-2xx response.
 */
async function post<T>(path: string, body: Record<string, string>): Promise<T> {
  const res = await fetch(`${INTERNAL_CRYPTO_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Internal-Service-Token': getToken(),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Internal crypto ${path} failed: ${res.status} ${text}`);
  }
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export interface KeygenResult {
  /** ML-KEM-768 encapsulation key — 1184 bytes */
  mlkemEk: Buffer;
  /** AES-GCM sealed decapsulation key — 2428 bytes */
  mlkemSealedDk: Buffer;
  /** KEM-wrapped DEK — 1148 bytes */
  wrappedDek: Buffer;
}

// ---------------------------------------------------------------------------
// Internal response shapes (mirror api/schemas/internal_crypto.py)
// ---------------------------------------------------------------------------

interface KeygenResponse {
  mlkem_ek_hex: string;
  mlkem_sealed_dk_hex: string;
  wrapped_dek_hex: string;
}

interface UnwrapSessionDekResponse {
  session_dek_wrapped_hex: string;
}

interface RewrapDekResponse {
  rewrapped_dek_hex: string;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Call POST /internal/crypto/keygen.
 *
 * Generates a new ML-KEM-768 keypair and DEK sealed with the caller-supplied
 * sealing_key. Returns the three blobs to store on the users row.
 *
 * @param sealingKey  32-byte key derived from near-phantom-auth passkey material
 */
export async function internalKeygen(sealingKey: Buffer): Promise<KeygenResult> {
  if (sealingKey.length !== 32) {
    throw new Error(
      `sealingKey must be 32 bytes, got ${sealingKey.length}`,
    );
  }
  const resp = await post<KeygenResponse>('/internal/crypto/keygen', {
    sealing_key_hex: sealingKey.toString('hex'),
  });
  return {
    mlkemEk: Buffer.from(resp.mlkem_ek_hex, 'hex'),
    mlkemSealedDk: Buffer.from(resp.mlkem_sealed_dk_hex, 'hex'),
    wrappedDek: Buffer.from(resp.wrapped_dek_hex, 'hex'),
  };
}

/**
 * Call POST /internal/crypto/unwrap-session-dek.
 *
 * Unseals the user's DEK and re-wraps it with SESSION_DEK_WRAP_KEY for storage
 * in session_dek_cache. The plaintext DEK never crosses the IPC boundary.
 *
 * @param sealingKey    32-byte sealing key (same key used at registration)
 * @param mlkemSealedDk users.mlkem_sealed_dk blob
 * @param wrappedDek    users.wrapped_dek blob
 * @returns             Session-wrapped DEK — store directly in session_dek_cache.encrypted_dek
 */
export async function internalUnwrapSessionDek(
  sealingKey: Buffer,
  mlkemSealedDk: Buffer,
  wrappedDek: Buffer,
): Promise<Buffer> {
  const resp = await post<UnwrapSessionDekResponse>(
    '/internal/crypto/unwrap-session-dek',
    {
      sealing_key_hex: sealingKey.toString('hex'),
      mlkem_sealed_dk_hex: mlkemSealedDk.toString('hex'),
      wrapped_dek_hex: wrappedDek.toString('hex'),
    },
  );
  return Buffer.from(resp.session_dek_wrapped_hex, 'hex');
}

/**
 * Call POST /internal/crypto/rewrap-dek.
 *
 * Re-encapsulates a session-wrapped DEK to a grantee's ML-KEM public key (D-25).
 * Used when a client grants accountant access.
 *
 * @param sessionDekWrapped   session_dek_cache.encrypted_dek blob
 * @param granteeMlkemEk      Accountant's users.mlkem_ek (1184 bytes)
 * @returns                   Rewrapped DEK — store in accountant_access.rewrapped_client_dek
 */
export async function internalRewrapDek(
  sessionDekWrapped: Buffer,
  granteeMlkemEk: Buffer,
): Promise<Buffer> {
  const resp = await post<RewrapDekResponse>('/internal/crypto/rewrap-dek', {
    session_dek_wrapped_hex: sessionDekWrapped.toString('hex'),
    grantee_mlkem_ek_hex: granteeMlkemEk.toString('hex'),
  });
  return Buffer.from(resp.rewrapped_dek_hex, 'hex');
}

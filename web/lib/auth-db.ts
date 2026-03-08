import { Pool } from 'pg';

let pool: Pool | null = null;

export function getAuthPool(): Pool {
  if (!pool) {
    pool = new Pool({
      connectionString: process.env.DATABASE_URL || 'postgres://neartax:lqxBcUTkcgZdzrNdqYxcsFVGEwkEldMx@localhost:5432/neartax',
    });
  }
  return pool;
}

export async function getUser(identifier: string) {
  const pool = getAuthPool();
  const result = await pool.query(
    'SELECT id, near_account_id, codename FROM users WHERE codename = $1 OR username = $2 OR near_account_id = $3',
    [identifier, identifier, identifier]
  );
  return result.rows[0];
}

export async function getPasskey(userId: number) {
  const pool = getAuthPool();
  const result = await pool.query(
    'SELECT * FROM passkeys WHERE user_id = $1 ORDER BY last_used_at DESC LIMIT 1',
    [userId]
  );
  return result.rows[0];
}

export async function getPasskeyByCredential(credentialId: string) {
  const pool = getAuthPool();
  const result = await pool.query(
    'SELECT * FROM passkeys WHERE credential_id = $1',
    [credentialId]
  );
  return result.rows[0];
}

export async function getUserById(userId: number) {
  const pool = getAuthPool();
  const result = await pool.query('SELECT * FROM users WHERE id = $1', [userId]);
  return result.rows[0];
}

export async function createSession(userId: number, sessionId: string, expiresAt: string) {
  const pool = getAuthPool();
  await pool.query(
    'INSERT INTO sessions (id, user_id, expires_at) VALUES ($1, $2, $3)',
    [sessionId, expiresAt]
  );
}

export async function getSession(sessionToken: string) {
  const pool = getAuthPool();
  const result = await pool.query(`
    SELECT s.*, u.near_account_id, u.codename, u.created_at
    FROM sessions s
    JOIN users u ON s.user_id = u.id
    WHERE s.id = $1 AND s.expires_at > NOW()
  `, [sessionToken]);
  return result.rows[0];
}

export async function deleteSession(sessionToken: string) {
  const pool = getAuthPool();
  await pool.query('DELETE FROM sessions WHERE id = $1', [sessionToken]);
}

export async function updatePasskeyCounter(passkeyId: string, newCounter: number) {
  const pool = getAuthPool();
  await pool.query('UPDATE passkeys SET counter = $1, last_used_at = NOW() WHERE id = $2', [newCounter, passkeyId]);
}

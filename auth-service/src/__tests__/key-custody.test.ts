/**
 * Tests for key-custody.ts
 * Uses Node.js built-in test runner (node:test) with tsx.
 *
 * key-custody functions are tested via the DI-friendly factory export
 * (_createKeyCustody) which accepts mock pool and client dependencies.
 * This avoids the need for ESM module-level mocking.
 *
 * Tables referenced (users.mlkem_ek, session_dek_cache) don't exist until
 * migration 022 (plan 16-04). These tests mock the pool so no real DB is needed.
 */

import { describe, test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import type { KeygenResult } from '../internal-crypto-client.js';
import { _createKeyCustody } from '../key-custody.js';

// ---------------------------------------------------------------------------
// Mock helpers
// ---------------------------------------------------------------------------

type MockPool = {
  query: MockFn;
};

type MockFn = {
  (...args: unknown[]): Promise<{ rows: Record<string, unknown>[] }>;
  calls: unknown[][];
  mockResolvedValueOnce: (val: { rows: Record<string, unknown>[] }) => MockFn;
  _queue: { rows: Record<string, unknown>[] }[];
};

function createMockFn(): MockFn {
  const calls: unknown[][] = [];
  const queue: { rows: Record<string, unknown>[] }[] = [];
  const fn: MockFn = Object.assign(
    async (...args: unknown[]) => {
      calls.push(args);
      if (queue.length > 0) {
        return queue.shift()!;
      }
      return { rows: [] };
    },
    {
      calls,
      _queue: queue,
      mockResolvedValueOnce(val: { rows: Record<string, unknown>[] }) {
        queue.push(val);
        return fn;
      },
    },
  );
  return fn;
}

function createMockPool(): MockPool {
  return { query: createMockFn() };
}

const FAKE_KEYGEN_RESULT: KeygenResult = {
  mlkemEk: Buffer.alloc(1184, 1),
  mlkemSealedDk: Buffer.alloc(2428, 2),
  wrappedDek: Buffer.alloc(1148, 3),
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('key-custody', () => {
  let pool: MockPool;
  let mockKeygen: MockFn;
  let mockUnwrap: MockFn;

  beforeEach(() => {
    pool = createMockPool();
    mockKeygen = createMockFn();
    mockUnwrap = createMockFn();
  });

  test('provisionUserKeys calls internalKeygen and writes three columns to users', async () => {
    mockKeygen.mockResolvedValueOnce(FAKE_KEYGEN_RESULT as unknown as { rows: Record<string, unknown>[] });
    pool.query.mockResolvedValueOnce({ rows: [] });

    const custody = _createKeyCustody(
      pool as unknown as import('pg').Pool,
      mockKeygen as unknown as (sealingKey: Buffer) => Promise<KeygenResult>,
      mockUnwrap as unknown as (
        sealingKey: Buffer,
        mlkemSealedDk: Buffer,
        wrappedDek: Buffer,
      ) => Promise<Buffer>,
    );

    await custody.provisionUserKeys(42, Buffer.alloc(32));

    assert.equal(mockKeygen.calls.length, 1);
    assert.equal(pool.query.calls.length, 1);
    const [sql, params] = pool.query.calls[0] as [string, unknown[]];
    assert.ok(sql.includes('UPDATE users SET mlkem_ek'), `SQL should update mlkem_ek, got: ${sql}`);
    assert.ok(sql.includes('mlkem_sealed_dk'), `SQL should include mlkem_sealed_dk, got: ${sql}`);
    assert.ok(sql.includes('wrapped_dek'), `SQL should include wrapped_dek, got: ${sql}`);
    assert.deepEqual(params, [FAKE_KEYGEN_RESULT.mlkemEk, FAKE_KEYGEN_RESULT.mlkemSealedDk, FAKE_KEYGEN_RESULT.wrappedDek, 42]);
  });

  test('resolveSessionDek fails when user has no key bundle', async () => {
    pool.query.mockResolvedValueOnce({ rows: [] }); // getUserKeyBundle returns empty

    const custody = _createKeyCustody(
      pool as unknown as import('pg').Pool,
      mockKeygen as unknown as (sealingKey: Buffer) => Promise<KeygenResult>,
      mockUnwrap as unknown as (
        sealingKey: Buffer,
        mlkemSealedDk: Buffer,
        wrappedDek: Buffer,
      ) => Promise<Buffer>,
    );

    await assert.rejects(
      () => custody.resolveSessionDek(42, 'sess-1', Buffer.alloc(32)),
      (err: Error) => {
        assert.ok(err.message.includes('no key bundle'), `Expected "no key bundle" in: ${err.message}`);
        return true;
      },
    );
  });

  test('resolveSessionDek writes session_dek_cache row with upsert', async () => {
    // First query: getUserKeyBundle
    pool.query.mockResolvedValueOnce({
      rows: [{
        mlkem_ek: Buffer.alloc(1184, 0xaa),
        mlkem_sealed_dk: Buffer.alloc(2428, 0xbb),
        wrapped_dek: Buffer.alloc(1148, 0xcc),
      }],
    });
    // Second query: INSERT INTO session_dek_cache
    pool.query.mockResolvedValueOnce({ rows: [] });

    // Mock the unwrap function
    mockUnwrap.mockResolvedValueOnce(Buffer.alloc(60, 0x07) as unknown as { rows: Record<string, unknown>[] });

    const custody = _createKeyCustody(
      pool as unknown as import('pg').Pool,
      mockKeygen as unknown as (sealingKey: Buffer) => Promise<KeygenResult>,
      mockUnwrap as unknown as (
        sealingKey: Buffer,
        mlkemSealedDk: Buffer,
        wrappedDek: Buffer,
      ) => Promise<Buffer>,
    );

    await custody.resolveSessionDek(42, 'sess-1', Buffer.alloc(32));

    assert.equal(pool.query.calls.length, 2);
    const [upsertSql, upsertParams] = pool.query.calls[1] as [string, unknown[]];
    assert.ok(upsertSql.includes('INSERT INTO session_dek_cache'), `SQL should insert into session_dek_cache, got: ${upsertSql}`);
    assert.equal(upsertParams[0], 'sess-1');
  });

  test('deleteSessionDekCache issues DELETE for session_id', async () => {
    pool.query.mockResolvedValueOnce({ rows: [] });

    const custody = _createKeyCustody(
      pool as unknown as import('pg').Pool,
      mockKeygen as unknown as (sealingKey: Buffer) => Promise<KeygenResult>,
      mockUnwrap as unknown as (
        sealingKey: Buffer,
        mlkemSealedDk: Buffer,
        wrappedDek: Buffer,
      ) => Promise<Buffer>,
    );

    await custody.deleteSessionDekCache('sess-1');

    assert.equal(pool.query.calls.length, 1);
    const [sql, params] = pool.query.calls[0] as [string, unknown[]];
    assert.ok(sql.includes('DELETE FROM session_dek_cache'), `SQL should delete from session_dek_cache, got: ${sql}`);
    assert.deepEqual(params, ['sess-1']);
  });
});

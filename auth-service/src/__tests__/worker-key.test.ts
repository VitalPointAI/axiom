/**
 * Tests for worker-key.ts
 * Uses Node.js built-in test runner (node:test) with tsx.
 *
 * Uses the _createWorkerKeyOps DI factory to inject mock pool + client deps.
 * The audit_log and users.worker_sealed_dek columns don't exist until
 * migration 022 (plan 16-04). These tests mock the pool — no real DB needed.
 */

import { describe, test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import type { KeygenResult } from '../internal-crypto-client.js';
import { _createWorkerKeyOps } from '../worker-key.js';

// ---------------------------------------------------------------------------
// Mock helpers (same pattern as key-custody.test.ts)
// ---------------------------------------------------------------------------

type MockFn<TReturn = unknown> = {
  (...args: unknown[]): Promise<TReturn>;
  calls: unknown[][];
  mockResolvedValueOnce: (val: TReturn) => MockFn<TReturn>;
  _queue: TReturn[];
};

function createMockFn<TReturn = unknown>(defaultReturn?: TReturn): MockFn<TReturn> {
  const calls: unknown[][] = [];
  const queue: TReturn[] = [];
  const fn: MockFn<TReturn> = Object.assign(
    async (...args: unknown[]) => {
      calls.push(args);
      if (queue.length > 0) {
        return queue.shift()!;
      }
      return (defaultReturn ?? { rows: [] }) as TReturn;
    },
    {
      calls,
      _queue: queue,
      mockResolvedValueOnce(val: TReturn) {
        queue.push(val);
        return fn;
      },
    },
  );
  return fn;
}

const KEY_BUNDLE: KeygenResult = {
  mlkemEk: Buffer.alloc(1184, 0xaa),
  mlkemSealedDk: Buffer.alloc(2428, 0xbb),
  wrappedDek: Buffer.alloc(1148, 0xcc),
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('worker-key', () => {
  let mockQuery: MockFn<{ rows: Record<string, unknown>[] }>;
  let mockGetBundle: MockFn<KeygenResult | null>;
  let mockUnwrap: MockFn<Buffer>;
  let mockRewrap: MockFn<Buffer>;

  beforeEach(() => {
    mockQuery = createMockFn({ rows: [] });
    mockGetBundle = createMockFn<KeygenResult | null>(null);
    mockUnwrap = createMockFn<Buffer>(Buffer.alloc(60, 0x07));
    mockRewrap = createMockFn<Buffer>(Buffer.alloc(1148, 0xdd));
  });

  test('createWorkerKey throws when user has no key bundle', async () => {
    mockGetBundle.mockResolvedValueOnce(null);

    const ops = _createWorkerKeyOps(
      { query: mockQuery } as unknown as import('pg').Pool,
      mockGetBundle as unknown as (userId: number) => Promise<KeygenResult | null>,
      mockUnwrap as unknown as (sealingKey: Buffer, mlkemSealedDk: Buffer, wrappedDek: Buffer) => Promise<Buffer>,
      mockRewrap as unknown as (sessionDekWrapped: Buffer, granteeMlkemEk: Buffer) => Promise<Buffer>,
    );

    await assert.rejects(
      () => ops.createWorkerKey(42, Buffer.alloc(32)),
      (err: Error) => {
        assert.ok(err.message.includes('no key bundle'), `Expected "no key bundle" in: ${err.message}`);
        return true;
      },
    );
  });

  test('createWorkerKey updates users and writes audit_log', async () => {
    mockGetBundle.mockResolvedValueOnce(KEY_BUNDLE);
    // Two pool.query calls: UPDATE users, INSERT audit_log
    mockQuery.mockResolvedValueOnce({ rows: [] });
    mockQuery.mockResolvedValueOnce({ rows: [] });

    const ops = _createWorkerKeyOps(
      { query: mockQuery } as unknown as import('pg').Pool,
      mockGetBundle as unknown as (userId: number) => Promise<KeygenResult | null>,
      mockUnwrap as unknown as (sealingKey: Buffer, mlkemSealedDk: Buffer, wrappedDek: Buffer) => Promise<Buffer>,
      mockRewrap as unknown as (sessionDekWrapped: Buffer, granteeMlkemEk: Buffer) => Promise<Buffer>,
    );

    await ops.createWorkerKey(42, Buffer.alloc(32));

    // Verify two DB calls were made
    assert.equal(mockQuery.calls.length, 2);

    // First call: UPDATE users SET worker_sealed_dek
    const [sql1] = mockQuery.calls[0] as [string, unknown[]];
    assert.ok(sql1.includes('UPDATE users'), `First SQL should update users, got: ${sql1}`);
    assert.ok(sql1.includes('worker_sealed_dek'), `First SQL should set worker_sealed_dek, got: ${sql1}`);
    assert.ok(sql1.includes('worker_key_enabled'), `First SQL should set worker_key_enabled, got: ${sql1}`);

    // Second call: INSERT audit_log
    const [sql2] = mockQuery.calls[1] as [string, unknown[]];
    assert.ok(sql2.includes('INSERT INTO audit_log'), `Second SQL should insert audit_log, got: ${sql2}`);
    assert.ok(sql2.includes('worker_key_enabled'), `Audit SQL should record worker_key_enabled, got: ${sql2}`);
  });

  test('revokeWorkerKey sets columns null/false and writes audit row', async () => {
    // Two pool.query calls: UPDATE users, INSERT audit_log
    mockQuery.mockResolvedValueOnce({ rows: [] });
    mockQuery.mockResolvedValueOnce({ rows: [] });

    const ops = _createWorkerKeyOps(
      { query: mockQuery } as unknown as import('pg').Pool,
      mockGetBundle as unknown as (userId: number) => Promise<KeygenResult | null>,
      mockUnwrap as unknown as (sealingKey: Buffer, mlkemSealedDk: Buffer, wrappedDek: Buffer) => Promise<Buffer>,
      mockRewrap as unknown as (sessionDekWrapped: Buffer, granteeMlkemEk: Buffer) => Promise<Buffer>,
    );

    await ops.revokeWorkerKey(42);

    assert.equal(mockQuery.calls.length, 2);

    // First call: UPDATE users SET worker_sealed_dek = NULL
    const [sql1] = mockQuery.calls[0] as [string, unknown[]];
    assert.ok(sql1.includes('UPDATE users'), `SQL should update users, got: ${sql1}`);
    assert.ok(sql1.includes('worker_sealed_dek'), `SQL should update worker_sealed_dek, got: ${sql1}`);
    assert.ok(
      sql1.includes('NULL') || sql1.includes('$1') || sql1.includes('null'),
      `SQL should null the column, got: ${sql1}`,
    );
    assert.ok(
      sql1.includes('worker_key_enabled'),
      `SQL should update worker_key_enabled, got: ${sql1}`,
    );

    // Second call: INSERT audit_log with revoked action
    const [sql2] = mockQuery.calls[1] as [string, unknown[]];
    assert.ok(sql2.includes('INSERT INTO audit_log'), `Should insert audit_log, got: ${sql2}`);
    assert.ok(sql2.includes('worker_key_revoked'), `Audit SQL should record worker_key_revoked, got: ${sql2}`);
  });
});

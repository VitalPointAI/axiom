/**
 * Tests for internal-crypto-client.ts
 * Uses Node.js built-in test runner (node:test) with tsx.
 *
 * NOTE: These tests mock global.fetch to avoid requiring a real FastAPI instance.
 * Real end-to-end testing against the running FastAPI is deferred to plan 16-07.
 */

import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';

// Helper to create a mock fetch that returns a specific response
type MockResponse = {
  ok: boolean;
  status?: number;
  json?: () => Promise<unknown>;
  text?: () => Promise<string>;
};

function mockFetch(response: MockResponse) {
  const calls: [string, RequestInit][] = [];
  const fn = async (url: string, init: RequestInit) => {
    calls.push([url, init]);
    return {
      ok: response.ok,
      status: response.status ?? (response.ok ? 200 : 401),
      json: response.json ?? (async () => ({})),
      text: response.text ?? (async () => ''),
    };
  };
  (fn as unknown as { calls: typeof calls }).calls = calls;
  return fn as unknown as typeof globalThis.fetch & { calls: typeof calls };
}

describe('internal-crypto-client', () => {
  const savedFetch = globalThis.fetch;
  const savedToken = process.env.INTERNAL_SERVICE_TOKEN;
  const savedUrl = process.env.INTERNAL_CRYPTO_URL;

  afterEach(() => {
    globalThis.fetch = savedFetch;
    if (savedToken !== undefined) {
      process.env.INTERNAL_SERVICE_TOKEN = savedToken;
    } else {
      delete process.env.INTERNAL_SERVICE_TOKEN;
    }
    if (savedUrl !== undefined) {
      process.env.INTERNAL_CRYPTO_URL = savedUrl;
    } else {
      delete process.env.INTERNAL_CRYPTO_URL;
    }
  });

  test('throws when INTERNAL_SERVICE_TOKEN is missing', async () => {
    delete process.env.INTERNAL_SERVICE_TOKEN;
    // Dynamic import to avoid module-level caching of env
    const { internalKeygen } = await import('../internal-crypto-client.js');
    await assert.rejects(
      () => internalKeygen(Buffer.alloc(32)),
      (err: Error) => {
        assert.ok(err.message.includes('INTERNAL_SERVICE_TOKEN not configured'));
        return true;
      },
    );
  });

  test('rejects non-32-byte sealing key', async () => {
    process.env.INTERNAL_SERVICE_TOKEN = 'test-token';
    const { internalKeygen } = await import('../internal-crypto-client.js');
    await assert.rejects(
      () => internalKeygen(Buffer.alloc(31)),
      (err: Error) => {
        assert.ok(err.message.includes('sealingKey must be 32 bytes'));
        return true;
      },
    );
  });

  test('posts hex-encoded sealing key and parses hex response', async () => {
    process.env.INTERNAL_SERVICE_TOKEN = 'test-token';
    process.env.INTERNAL_CRYPTO_URL = 'http://localhost:8000';

    const mockResponse = {
      mlkem_ek_hex: 'aa'.repeat(1184),
      mlkem_sealed_dk_hex: 'bb'.repeat(2428),
      wrapped_dek_hex: 'cc'.repeat(1148),
    };

    const fetcher = mockFetch({
      ok: true,
      json: async () => mockResponse,
    });
    globalThis.fetch = fetcher;

    const { internalKeygen } = await import('../internal-crypto-client.js');
    const result = await internalKeygen(Buffer.alloc(32, 0x42));

    assert.equal(result.mlkemEk.length, 1184);
    assert.equal(result.mlkemSealedDk.length, 2428);
    assert.equal(result.wrappedDek.length, 1148);

    // Verify the request was made correctly
    const [url, init] = fetcher.calls[0];
    assert.ok(url.includes('/internal/crypto/keygen'));
    const headers = init.headers as Record<string, string>;
    assert.equal(headers['X-Internal-Service-Token'], 'test-token');
    const body = JSON.parse(init.body as string) as Record<string, string>;
    assert.equal(body.sealing_key_hex, '42'.repeat(32));
  });

  test('throws on non-ok response', async () => {
    process.env.INTERNAL_SERVICE_TOKEN = 'test-token';

    globalThis.fetch = mockFetch({
      ok: false,
      status: 401,
      text: async () => 'Unauthorized',
    });

    const { internalKeygen } = await import('../internal-crypto-client.js');
    await assert.rejects(
      () => internalKeygen(Buffer.alloc(32)),
      (err: Error) => {
        assert.ok(err.message.includes('401'));
        assert.ok(err.message.includes('Unauthorized'));
        return true;
      },
    );
  });
});

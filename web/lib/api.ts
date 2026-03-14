/**
 * Centralized API client for all FastAPI communication.
 * All requests include credentials: 'include' for cross-origin cookie auth.
 */

// In production, API calls use relative paths (proxied via Next.js rewrites).
// For local dev, set NEXT_PUBLIC_API_URL=http://localhost:8000 in .env.local.
export const API_URL = process.env.NEXT_PUBLIC_API_URL || '';

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`API error ${status}`);
    this.name = 'ApiError';
  }
}

async function request(path: string, init: RequestInit = {}): Promise<unknown> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...init.headers,
    },
  });

  if (!res.ok) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = { detail: res.statusText };
    }
    throw new ApiError(res.status, body);
  }

  // 204 No Content — return null
  if (res.status === 204) return null;

  return res.json();
}

export const apiClient = {
  get<T = unknown>(path: string, opts?: RequestInit): Promise<T> {
    return request(path, { method: 'GET', ...opts }) as Promise<T>;
  },

  post<T = unknown>(path: string, body?: unknown, opts?: RequestInit): Promise<T> {
    return request(path, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
      ...opts,
    }) as Promise<T>;
  },

  patch<T = unknown>(path: string, body?: unknown, opts?: RequestInit): Promise<T> {
    return request(path, {
      method: 'PATCH',
      body: body !== undefined ? JSON.stringify(body) : undefined,
      ...opts,
    }) as Promise<T>;
  },

  delete<T = unknown>(path: string, opts?: RequestInit): Promise<T> {
    return request(path, { method: 'DELETE', ...opts }) as Promise<T>;
  },
};

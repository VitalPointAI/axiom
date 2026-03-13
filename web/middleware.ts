import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Auth and rate limiting are handled by the FastAPI backend.
// This middleware handles:
// 1. Redirecting unauthenticated users to /auth for dashboard pages
// 2. Adding security headers to all responses

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // === PUBLIC ROUTES (no auth check needed) ===
  const publicPaths = [
    '/auth',       // Auth page
    '/_next',      // Next.js internals
    '/favicon.ico',
    '/robots.txt',
  ];

  if (publicPaths.some(path => pathname.startsWith(path))) {
    const response = NextResponse.next();
    addSecurityHeaders(response);
    return response;
  }

  // === PROTECTED DASHBOARD ROUTES ===
  // FastAPI validates session tokens on all API calls.
  // Here we just redirect unauthenticated users away from dashboard pages.
  if (pathname.startsWith('/dashboard')) {
    const sessionCookie = request.cookies.get('neartax_session');
    if (!sessionCookie?.value) {
      return NextResponse.redirect(new URL('/auth', request.url));
    }
  }

  // === SECURITY HEADERS ===
  const response = NextResponse.next();
  addSecurityHeaders(response);
  return response;
}

function addSecurityHeaders(response: NextResponse) {
  response.headers.set('X-Content-Type-Options', 'nosniff');
  response.headers.set('X-Frame-Options', 'DENY');
  response.headers.set('X-XSS-Protection', '1; mode=block');
  response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
}

// Configure which routes middleware applies to
export const config = {
  matcher: [
    // Match all routes except static files
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};

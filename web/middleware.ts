import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// Rate limiting store (in-memory - resets on restart)
// For production with multiple servers, use Redis
const rateLimitStore = new Map<string, { count: number; resetTime: number }>();

// Rate limit config
const RATE_LIMIT_WINDOW_MS = 60 * 1000; // 1 minute
const RATE_LIMIT_MAX_REQUESTS = {
  auth: 500,      // 10 auth attempts per minute
  api: 100,      // 100 API calls per minute
  default: 200,  // 200 requests per minute
};

function getRateLimitKey(request: NextRequest): string {
  // Use IP + path prefix for rate limiting
  const ip = request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() 
    || request.headers.get('x-real-ip') 
    || 'unknown';
  
  if (request.nextUrl.pathname.startsWith('/api/phantom-auth')) {
    return `auth:${ip}`;
  }
  if (request.nextUrl.pathname.startsWith('/api/')) {
    return `api:${ip}`;
  }
  return `default:${ip}`;
}

function checkRateLimit(key: string, maxRequests: number): { allowed: boolean; remaining: number; resetIn: number } {
  const now = Date.now();
  const record = rateLimitStore.get(key);
  
  if (!record || now > record.resetTime) {
    // New window
    rateLimitStore.set(key, { count: 1, resetTime: now + RATE_LIMIT_WINDOW_MS });
    return { allowed: true, remaining: maxRequests - 1, resetIn: RATE_LIMIT_WINDOW_MS };
  }
  
  if (record.count >= maxRequests) {
    return { allowed: false, remaining: 0, resetIn: record.resetTime - now };
  }
  
  record.count++;
  return { allowed: true, remaining: maxRequests - record.count, resetIn: record.resetTime - now };
}

// Clean up old entries periodically (prevent memory leak)
setInterval(() => {
  const now = Date.now();
  for (const [key, record] of rateLimitStore.entries()) {
    if (now > record.resetTime) {
      rateLimitStore.delete(key);
    }
  }
}, 60 * 1000); // Clean every minute

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  
  // === RATE LIMITING ===
  const rateLimitKey = getRateLimitKey(request);
  const limitType = rateLimitKey.split(':')[0] as keyof typeof RATE_LIMIT_MAX_REQUESTS;
  const maxRequests = RATE_LIMIT_MAX_REQUESTS[limitType] || RATE_LIMIT_MAX_REQUESTS.default;
  
  const rateLimit = checkRateLimit(rateLimitKey, maxRequests);
  
  if (!rateLimit.allowed) {
    return NextResponse.json(
      { error: 'Too many requests. Please try again later.' },
      { 
        status: 429,
        headers: {
          'Retry-After': String(Math.ceil(rateLimit.resetIn / 1000)),
          'X-RateLimit-Limit': String(maxRequests),
          'X-RateLimit-Remaining': '0',
          'X-RateLimit-Reset': String(Math.ceil(rateLimit.resetIn / 1000)),
        }
      }
    );
  }
  
  // === PUBLIC ROUTES (no auth required) ===
  const publicPaths = [
    '/api/phantom-auth',     // Auth endpoints
    '/api/health',           // Health check
    '/auth',                 // Auth page
    '/_next',                // Next.js internals
    '/favicon.ico',
    '/robots.txt',
  ];
  
  if (publicPaths.some(path => pathname.startsWith(path))) {
    const response = NextResponse.next();
    response.headers.set('X-RateLimit-Remaining', String(rateLimit.remaining));
    return response;
  }
  
  // === PROTECTED ROUTES ===
  // Dashboard pages and API routes require authentication
  const protectedPaths = [
    '/dashboard',
    '/api/wallets',
    '/api/transactions',
    '/api/portfolio',
    '/api/staking',
    '/api/defi',
    '/api/assets',
    '/api/reports',
    '/api/sync',
    '/api/indexers',
    '/api/import',
    '/api/exchange',
    '/api/admin',
    '/api/settings',
    '/api/user',
    '/api/accountant',
  ];
  
  const isProtected = protectedPaths.some(path => pathname.startsWith(path));
  
  if (isProtected) {
    const sessionCookie = request.cookies.get('neartax_session');
    
    if (!sessionCookie?.value) {
      // No session cookie - reject immediately
      if (pathname.startsWith('/api/')) {
        return NextResponse.json(
          { error: 'Authentication required' },
          { status: 401 }
        );
      }
      // Redirect pages to auth
      return NextResponse.redirect(new URL('/auth', request.url));
    }
    
    // Session cookie exists - let the route handler validate it
    // This is defense in depth: middleware blocks no-cookie, routes validate the token
  }
  
  // === ADMIN ROUTES - Extra check ===
  // Admin routes have additional protection (actual admin check happens in route)
  if (pathname.startsWith('/api/admin') || pathname.startsWith('/dashboard/admin')) {
    const sessionCookie = request.cookies.get('neartax_session');
    if (!sessionCookie?.value) {
      return NextResponse.json(
        { error: 'Admin access required' },
        { status: 403 }
      );
    }
    // Admin flag check happens in the route handler
  }
  
  // === SECURITY HEADERS ===
  const response = NextResponse.next();
  
  // Add security headers
  response.headers.set('X-Content-Type-Options', 'nosniff');
  response.headers.set('X-Frame-Options', 'DENY');
  response.headers.set('X-XSS-Protection', '1; mode=block');
  response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  response.headers.set('X-RateLimit-Remaining', String(rateLimit.remaining));
  
  return response;
}

// Configure which routes middleware applies to
export const config = {
  matcher: [
    // Match all routes except static files
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};

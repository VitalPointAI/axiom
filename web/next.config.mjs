/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: false,
  transpilePackages: ['@aurora-is-near/intents-swap-widget'],
  // Force cache busting for the auth fix
  generateBuildId: async () => {
    return 'build-' + Date.now();
  },
  // Expose FastAPI base URL to the browser
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
  async headers() {
    return [
      {
        source: '/(features|pricing|privacy|compliance|about)',
        headers: [{ key: 'Cache-Control', value: 's-maxage=3600, stale-while-revalidate=86400' }],
      },
      {
        source: '/',
        headers: [{ key: 'Cache-Control', value: 's-maxage=3600, stale-while-revalidate=86400' }],
      },
      {
        source: '/dashboard/:path*',
        headers: [{ key: 'Cache-Control', value: 'no-store, must-revalidate' }],
      },
      {
        source: '/auth/:path*',
        headers: [{ key: 'Cache-Control', value: 'no-store, must-revalidate' }],
      },
      {
        source: '/api/:path*',
        headers: [{ key: 'Cache-Control', value: 'no-store, must-revalidate' }],
      },
    ];
  },
};

export default nextConfig;

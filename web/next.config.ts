import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://api:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backend}/api/:path*`,
      },
      {
        source: "/auth/:path*",
        destination: `${backend}/auth/:path*`,
      },
      {
        source: "/health",
        destination: `${backend}/health`,
      },
    ];
  },
};

export default nextConfig;

import type { NextConfig } from "next";

// Server-only. The browser never sees this; it calls the relative /api path.
const BACKEND = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // gzip in `next start` buffers SSE frames; the stream must pass through as is.
  compress: false,
  async rewrites() {
    // Single origin in dev: no CORS, and SSE passes straight through.
    return [{ source: "/api/:path*", destination: `${BACKEND}/api/:path*` }];
  },
};

export default nextConfig;
